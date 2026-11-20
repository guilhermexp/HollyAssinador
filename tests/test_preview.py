"""A área escolhida na tela deve abranger a assinatura, inclusive em PDF girado."""

import tempfile
import unittest
from pathlib import Path

from PIL import ImageChops
from pyhanko.pdf_utils import generic
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from reportlab.pdfgen.canvas import Canvas

from preview import ordered, render_page
from signer_core import MarkedBox, SignatureOptions, SigningError, sign_pdf_a1
from tests import apoio


class PlacementTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name).resolve()
        self.cert = apoio.a1(self.folder)
        src = self.folder / "base.pdf"
        c = Canvas(str(src), pagesize=(520, 740))
        for i in range(4):
            c.drawString(40, 660, f"Folha {i + 1}")
            c.showPage()
        c.save()
        self.src = self.folder / "paginas.pdf"
        with src.open("rb") as inf, self.src.open("wb") as out:
            writer = IncrementalPdfFileWriter(inf)
            for i in range(4):
                ref, _ = writer.find_page_for_modification(i)
                page = ref.get_object()
                page["/Rotate"] = generic.NumberObject(i * 90)
                page["/CropBox"] = generic.ArrayObject(
                    map(generic.NumberObject, (23, 45, 501, 700))
                )
                writer.update_container(page)
            writer.write(out)

    def mark(self, page=0):
        view = render_page(self.src, page, (600, 600), 1)
        rect = ordered(*view.to_page(48, 110), *view.to_page(300, 195))
        return view, MarkedBox(self.src, view.revision, page, rect, view.rotation)

    def test_pagina_recorte_rotacao_e_assinatura_valida(self):
        first_ink = None
        for i in range(4):
            with self.subTest(rotation=i * 90):
                before, mark = self.mark(i)
                out = self.folder / f"saida-{i}.pdf"
                sign_pdf_a1(
                    self.src,
                    out,
                    self.cert,
                    apoio.SENHA,
                    SignatureOptions(appearance="manual", placements=(mark,)),
                )
                self.assertTrue(apoio.assinatura_valida(out))
                after = render_page(out, i, (600, 600), 1)
                ink = ImageChops.difference(before.image, after.image).getbbox()
                self.assertIsNotNone(ink)
                self.assertTrue(48 <= ink[0] < ink[2] <= 300)
                self.assertTrue(110 <= ink[1] < ink[3] <= 195)
                if first_ink is None:
                    first_ink = ink
                for actual, expected in zip(ink, first_ink):
                    self.assertAlmostEqual(actual, expected, delta=2)

    def test_segunda_assinatura_preserva_a_primeira(self):
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.sign.validation import validate_pdf_signature
        from pyhanko_certvalidator import ValidationContext

        first = self.folder / "primeira.pdf"
        sign_pdf_a1(self.src, first, self.cert, apoio.SENHA, SignatureOptions())
        self.src = first
        _, mark = self.mark(2)
        final = self.folder / "segunda.pdf"
        sign_pdf_a1(
            first,
            final,
            self.cert,
            apoio.SENHA,
            SignatureOptions(appearance="manual", placements=(mark,)),
        )
        self.assertTrue(final.read_bytes().startswith(first.read_bytes()))
        with final.open("rb") as stream:
            signatures = PdfFileReader(stream).embedded_signatures
            self.assertEqual(len(signatures), 2)
            for signature in signatures:
                trust = ValidationContext(trust_roots=[signature.signer_cert])
                state = validate_pdf_signature(signature, trust)
                self.assertTrue(state.valid and state.intact)

    def test_documento_alterado_recusa_marcacao(self):
        _, mark = self.mark()
        with self.src.open("ab") as out:
            out.write(b"\n")
        dest = self.folder / "saida.pdf"
        with self.assertRaisesRegex(SigningError, "mudou"):
            sign_pdf_a1(
                self.src,
                dest,
                self.cert,
                apoio.SENHA,
                SignatureOptions(appearance="manual", placements=(mark,)),
            )
        self.assertFalse(dest.exists())
