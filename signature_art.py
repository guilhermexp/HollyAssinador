"""A mesma composição vetorial para o widget do PDF e para o painel de prévia."""

from dataclasses import dataclass
from io import BytesIO

from pyhanko import stamp
from pyhanko.pdf_utils import content, generic
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.stamp.base import BaseStamp
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas


def _lines(text, width, size):
    lines = []
    for paragraph in text.splitlines():
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}" if line else word
            if stringWidth(candidate, "Helvetica", size) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
            line = ""
            for char in word:
                if line and stringWidth(line + char, "Helvetica", size) > width:
                    lines.append(line)
                    line = ""
                line += char
        if line:
            lines.append(line)
    return lines


def _column(canvas, text, left, width, height, maximum):
    low, high = 0.05, maximum
    for _ in range(13):
        mid = (low + high) / 2
        lines = _lines(text, width, mid)
        if len(lines) * mid * 1.14 <= height:
            low = mid
        else:
            high = mid
    lines = _lines(text, width, low)
    leading = low * 1.14
    baseline = (height + len(lines) * leading) / 2 - low * 0.89
    canvas.setFont("Helvetica", low)
    for line in lines:
        canvas.drawString(left, baseline, line)
        baseline -= leading


def stamp_pdf(width, height, name, timestamp, rotation=0):
    output = BytesIO()
    c = Canvas(output, pagesize=(width, height), pageCompression=1)
    if rotation == 90:
        c.translate(width, 0)
    elif rotation == 180:
        c.translate(width, height)
    elif rotation == 270:
        c.translate(0, height)
    c.rotate(rotation)
    if rotation in (90, 270):
        width, height = height, width

    # Traço original em rosa claro atrás da divisão entre as duas colunas.
    c.saveState()
    scale = min(height * 0.95, width * 0.36)
    c.translate(width * 0.49 - scale / 2, (height - scale) / 2)
    c.scale(scale, scale)
    c.setStrokeColorRGB(0.99, 0.86, 0.87)
    c.setLineWidth(0.014)
    c.setLineCap(1)
    p = c.beginPath()
    p.moveTo(0.08, 0.07)
    p.curveTo(0.18, -0.02, 0.73, 0.96, 0.52, 0.96)
    p.curveTo(0.36, 0.94, 0.53, 0.30, 0.86, 0.34)
    p.curveTo(1.02, 0.40, 0.39, 0.47, 0.08, 0.07)
    c.drawPath(p)
    c.restoreState()
    name = " ".join(name.split()) or "Titular do certificado"
    width_half = width * 0.485
    _column(c, name, width * 0.005, width_half, height, min(height * 0.49, width * 0.076))
    _column(
        c,
        f"Assinado de forma digital por {name}\nDados: {timestamp}",
        width * 0.515,
        width * 0.48,
        height,
        min(height * 0.25, width * 0.046),
    )
    c.showPage()
    c.save()
    return output.getvalue()


def date_label(raw):
    # %z entrega +HHMM. A referência usa +HH'mm'.
    return raw[:-2] + "'" + raw[-2:] + "'"


class _SignatureStamp(BaseStamp):
    def __init__(self, writer, style, box, params):
        super().__init__(writer, style, box)
        self.params = params

    def _render_inner_content(self):
        pdf = stamp_pdf(
            self.box.width,
            self.box.height,
            self.params["signer"],
            date_label(self.params["ts"]),
            self.style.rotation,
        )
        ref = self.writer.import_page_as_xobject(PdfFileReader(BytesIO(pdf)))
        self.set_resource(content.ResourceType.XOBJECT, generic.pdf_name("/SignatureArt"), ref)
        return [b"/SignatureArt Do"]


@dataclass(frozen=True)
class SignatureStyle(stamp.TextStampStyle):
    rotation: int = 0
    border_width: int = 0
    timestamp_format: str = "%Y.%m.%d %H:%M:%S %z"

    def create_stamp(self, writer, box, text_params):
        return _SignatureStamp(writer, self, box, text_params)
