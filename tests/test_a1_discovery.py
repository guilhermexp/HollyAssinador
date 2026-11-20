from pathlib import Path
from queue import SimpleQueue
from tempfile import TemporaryDirectory
from subprocess import CompletedProcess
from unittest import TestCase, mock, skipUnless

import Security as sec

from a1_files import discover_a1_files
from app import AssinadorApp
from macos_token import discover_keychain_a1
from selftest import _pdf_bytes, _pkcs12_bytes
from signer_core import SignatureOptions
from tests.apoio import assinatura_valida


class A1DiscoveryTests(TestCase):
    def test_busca_por_nome_inclui_spotlight_e_pastas_sem_indice(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            indexed = home / "Projetos" / "local.p12"
            downloaded = home / "Downloads" / "Pasta" / "pessoal.PFX"
            hidden = home / ".dados" / "interno.p12"
            for p in (indexed, downloaded, hidden):
                p.parent.mkdir(parents=True)
                p.touch()
            output = b"\0".join(bytes(p) for p in (indexed, downloaded, hidden))
            with mock.patch("a1_files.subprocess.run", return_value=CompletedProcess([], 0, output)):
                self.assertEqual(set(discover_a1_files(home)), {indexed, downloaded})

    @skipUnless(hasattr(sec, "kSecImportToMemoryOnly"), "requer importação em memória")
    def test_assina_com_identidade_do_sistema_sem_pfx_ou_senha_no_job(self):
        pfx, _ = _pkcs12_bytes(b"teste")
        status, items = sec.SecPKCS12Import(pfx, {
            sec.kSecImportExportPassphrase: "teste", sec.kSecImportToMemoryOnly: True,
        }, None)
        self.assertEqual(status, sec.errSecSuccess)
        identity = items[0][sec.kSecImportItemIdentity]

        def query(item_class, context, token_id=None, *, keychains=None):
            self.assertIsNotNone(keychains)
            if item_class == sec.kSecClassIdentity:
                return [{sec.kSecValueRef: identity}, {sec.kSecValueRef: identity, sec.kSecAttrTokenID: "A3"}]
            return []

        with mock.patch("macos_token._items", side_effect=query), TemporaryDirectory() as tmp:
            identities = discover_keychain_a1()
            self.assertEqual(len(identities), 1)
            src, dst = (Path(tmp) / name for name in ("entrada.pdf", "saida.pdf"))
            src.write_bytes(_pdf_bytes())
            job = {"type": "A1", "keychain_identity": identities[0], "pairs": [(src, dst)]}
            events = SimpleQueue()
            AssinadorApp._sign_worker(job, SignatureOptions(), events)
            kind, results = events.get_nowait()
            self.assertEqual(kind, "done", results)
            self.assertIsNone(results[0].error)
            self.assertTrue(assinatura_valida(dst))
