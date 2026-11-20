"""Cobertura do caminho Security.framework com chave efêmera fora do Chaves."""
import asyncio
import queue
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from asn1crypto import x509 as asn_x509
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import pkcs12
import Security as sec

from app import AssinadorApp
from macos_token import MacTokenSigner, TokenCertificate, open_mac_token
from selftest import _pkcs12_bytes, _pdf_bytes
from signer_core import SignatureOptions, SigningError
from tests.apoio import assinatura_valida


class NativeTokenTests(unittest.TestCase):
    def setUp(self):
        blob, cert = _pkcs12_bytes(b"teste")
        key, _, _ = pkcs12.load_key_and_certificates(blob, b"teste")
        self.cert = asn_x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER))
        key_der = key.private_bytes(serialization.Encoding.DER,
                                    serialization.PrivateFormat.TraditionalOpenSSL,
                                    serialization.NoEncryption())
        self.key, error = sec.SecKeyCreateWithData(key_der, {
            sec.kSecAttrKeyClass: sec.kSecAttrKeyClassPrivate,
            sec.kSecAttrKeyType: sec.kSecAttrKeyTypeRSA,
        }, None)
        self.assertIsNone(error)

    def test_selecao_chega_ao_assinador_e_assina_lote(self):
        selected = TokenCertificate("cartão de teste", self.cert.dump())
        signer = MacTokenSigner(self.cert, self.key, [])

        @contextmanager
        def open_test(item, pin):
            self.assertEqual(item, selected)
            self.assertEqual(pin, "PIN de teste")
            yield signer

        with tempfile.TemporaryDirectory() as folder, patch("app.open_mac_token", open_test):
            src = Path(folder) / "entrada.pdf"
            src.write_bytes(_pdf_bytes())
            pairs = [(src, Path(folder) / f"assinado{i}.pdf") for i in range(2)]
            events = queue.SimpleQueue()
            job = {"type": "A3", "pairs": pairs, "token": selected, "a3_pin": "PIN de teste"}
            AssinadorApp._sign_worker(job, SignatureOptions(), events)
            while True:
                kind, result = events.get_nowait()
                if kind != "progress":
                    break
            self.assertEqual(kind, "done", result)
            self.assertNotIn("a3_pin", job)
            for outcome in result:
                self.assertIsNone(outcome.error)
                self.assertTrue(assinatura_valida(outcome.dst))

    def test_ec_assina_sha256_sem_acionar_token_na_estimativa(self):
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "Teste EC")])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(1)
                .not_valid_before(now).not_valid_after(now + timedelta(days=1))
                .sign(key, hashes.SHA256()))
        public = key.public_key().public_bytes(serialization.Encoding.X962,
                                              serialization.PublicFormat.UncompressedPoint)
        raw_key = public + key.private_numbers().private_value.to_bytes(32, "big")
        ref, error = sec.SecKeyCreateWithData(raw_key, {
            sec.kSecAttrKeyClass: sec.kSecAttrKeyClassPrivate,
            sec.kSecAttrKeyType: sec.kSecAttrKeyTypeECSECPrimeRandom,
        }, None)
        self.assertIsNone(error)
        signer = MacTokenSigner(asn_x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER)), ref, [])
        with patch.object(sec, "SecKeyCreateSignature") as call:
            reserved = asyncio.run(signer.async_sign_raw(b"teste", "sha256", dry_run=True))
            call.assert_not_called()
        signature = asyncio.run(signer.async_sign_raw(b"teste", "sha256"))
        self.assertGreaterEqual(len(reserved), len(signature))
        key.public_key().verify(signature, b"teste", ec.ECDSA(hashes.SHA256()))

    def test_cartao_trocado_recusado_antes_de_aplicar_pin(self):
        selected = TokenCertificate("token A", self.cert.dump())
        with patch("macos_token._identities", return_value=[]), self.assertRaisesRegex(SigningError, "saiu"):
            with open_mac_token(selected, "PIN de teste"):
                self.fail("assinador aberto para cartão ausente")

    def test_erro_do_dispositivo_nao_repete_tentativa_no_lote(self):
        signer = MacTokenSigner(self.cert, self.key, [])
        with patch.object(sec, "SecKeyCreateSignature", return_value=(None, None)) as call:
            for _ in range(2):
                with self.assertRaises(SigningError):
                    asyncio.run(signer.async_sign_raw(b"teste", "sha256"))
            call.assert_called_once()
