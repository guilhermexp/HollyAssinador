"""Prévia local e seleção de uma área por documento, em coordenadas do PDF."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from PIL import ImageTk
import pypdfium2 as pdfium

from placement import PDFIUM_LOCK
from signature_art import date_label, stamp_pdf
from signer_core import MarkedBox


@dataclass
class PageView:
    image: object
    count: int
    rotation: int
    revision: tuple
    origin: tuple
    dx: tuple
    dy: tuple

    def to_page(self, x, y):
        return tuple(self.origin[i] + x * self.dx[i] + y * self.dy[i] for i in (0, 1))

    def to_pixel(self, x, y):
        x, y = x - self.origin[0], y - self.origin[1]
        a, b = self.dx
        c, d = self.dy
        return ((d * x - c * y) / (a * d - b * c), (a * y - b * x) / (a * d - b * c))


def render_page(path, index, viewport, zoom):
    # O mesmo descritor fornece tanto a imagem quanto a revisão vinculada à marcação.
    import os

    with PDFIUM_LOCK, path.open("rb") as stream, pdfium.PdfDocument(stream) as doc:
        revision = MarkedBox.file_revision(os.fstat(stream.fileno()))
        doc.init_forms()
        with closing(doc[index]) as page:
            w, h = page.get_size()
            scale = zoom or min(viewport[0] / w, viewport[1] / h)
            scale = min(scale, 3000 / max(w, h))
            with closing(page.render(scale=scale, draw_annots=True)) as bitmap:
                image = bitmap.to_pil().convert("RGB")
                converter = bitmap.get_posconv(page)
                origin = converter.to_page(0, 0)
                xend = converter.to_page(bitmap.width, 0)
                yend = converter.to_page(0, bitmap.height)
                dx = tuple((xend[i] - origin[i]) / bitmap.width for i in (0, 1))
                dy = tuple((yend[i] - origin[i]) / bitmap.height for i in (0, 1))
            return PageView(image, len(doc), page.get_rotation(), revision, origin, dx, dy)


def ordered(x0, y0, x1, y1):
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


class Preview(ttk.Frame):
    def __init__(self, parent, on_mark, signer_name, close):
        super().__init__(parent, padding=(0, 10, 10, 10))
        self.on_mark, self.signer_name = on_mark, signer_name
        self.paths = []
        self.marks = {}
        self.page_index = 0
        self.view = self.drag = self.pending = None
        self.page_photo = self.art_photo = None
        self.show_mark = True
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew")
        bar.columnconfigure(1, weight=1)
        self.back = ttk.Button(bar, text="‹", width=3, command=lambda: self.turn(-1))
        self.back.grid(row=0, column=0)
        self.counter = ttk.Label(bar, text="Página", anchor="center")
        self.counter.grid(row=0, column=1)
        self.next = ttk.Button(bar, text="›", width=3, command=lambda: self.turn(1))
        self.next.grid(row=0, column=2)
        self.zoom = ttk.Combobox(
            bar, state="readonly", width=10, values=("Ajustar", "100%", "150%", "200%")
        )
        self.zoom.current(0)
        self.zoom.grid(row=0, column=3, padx=6)
        self.zoom.bind("<<ComboboxSelected>>", lambda _: self.schedule())
        ttk.Button(bar, text="Fechar", command=close).grid(row=0, column=4)
        self.documents = ttk.Combobox(self, state="readonly")
        self.documents.bind("<<ComboboxSelected>>", lambda _: self.select_document())
        self.canvas = c = tk.Canvas(
            self,
            width=320,
            height=360,
            background="#dfe1e4",
            highlightthickness=0,
            cursor="crosshair",
        )
        c.grid(row=2, column=0, sticky="nsew", pady=(6, 0))
        sy = ttk.Scrollbar(self, orient="vertical", command=c.yview)
        sx = ttk.Scrollbar(self, orient="horizontal", command=c.xview)
        sy.grid(row=2, column=1, sticky="ns", pady=(6, 0))
        sx.grid(row=3, column=0, sticky="ew")
        c.configure(xscrollcommand=sx.set, yscrollcommand=sy.set)
        self.hint = tk.StringVar(value="Arraste para marcar. Mova a caixa ou ajuste pelos cantos.")
        ttk.Label(self, textvariable=self.hint, wraplength=430).grid(
            row=4, column=0, sticky="w", pady=(5, 0)
        )
        c.bind("<Configure>", lambda _: self.schedule())
        c.bind("<ButtonPress-1>", self.press)
        c.bind("<B1-Motion>", self.motion)
        c.bind("<ButtonRelease-1>", self.release)
        c.bind("<MouseWheel>", lambda e: c.yview_scroll(-e.delta, "units"))

    @property
    def path(self):
        return self.paths[max(0, self.documents.current())] if self.paths else None

    def load(self, paths):
        paths = [Path(p).expanduser().resolve() for p in paths]
        if paths != self.paths:
            self.marks = {k: v for k, v in self.marks.items() if k in paths}
            self.paths = paths
            self.documents.configure(values=[f"{i + 1}. {p.name}" for i, p in enumerate(paths)])
            if paths:
                self.documents.current(0)
            if len(paths) > 1:
                self.documents.grid(row=1, column=0, sticky="ew", pady=(4, 0))
            else:
                self.documents.grid_remove()
        self.select_document()

    def select_document(self):
        mark = self.marks.get(self.path)
        self.page_index = mark.page if mark else 0
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.schedule()

    def turn(self, step):
        if self.view and 0 <= self.page_index + step < self.view.count:
            self.page_index += step
            self.canvas.yview_moveto(0)
            self.schedule()

    def schedule(self):
        self.view = self.drag = None
        if self.pending:
            self.after_cancel(self.pending)
        self.pending = self.after(45, self.render)

    def render(self):
        self.pending = None
        if not self.path or not self.winfo_ismapped():
            return
        c = self.canvas
        w, h = max(60, c.winfo_width()), max(60, c.winfo_height())
        zoom = (None, 1.0, 1.5, 2.0)[self.zoom.current()]
        try:
            self.view = render_page(self.path, self.page_index, (w - 16, h - 16), zoom)
        except Exception:
            self.view = None
            c.delete("all")
            c.create_text(
                w / 2, h / 2, width=w - 25, text="Não foi possível abrir esta página do PDF."
            )
            self.marks.pop(self.path, None)
            return
        page = self.view
        if self.path in self.marks and self.marks[self.path].revision != page.revision:
            del self.marks[self.path]
        self.back.configure(state="normal" if self.page_index else "disabled")
        self.next.configure(state="normal" if self.page_index + 1 < page.count else "disabled")
        self.counter.configure(text=f"Página {self.page_index + 1} de {page.count}")
        iw, ih = page.image.size
        self.ox, self.oy = max(8, (w - iw) // 2), max(8, (h - ih) // 2)
        c.delete("all")
        c.configure(scrollregion=(0, 0, max(w, iw + 16), max(h, ih + 16)))
        self.page_photo = ImageTk.PhotoImage(page.image)
        c.create_image(self.ox, self.oy, anchor="nw", image=self.page_photo)
        self.paint_mark()

    def pixel_rect(self):
        mark = self.marks.get(self.path)
        if not self.view or not self.show_mark or not mark or mark.page != self.page_index:
            return None
        return ordered(*self.view.to_pixel(*mark.rect[:2]), *self.view.to_pixel(*mark.rect[2:]))

    def paint_mark(self, rect=None):
        c = self.canvas
        c.delete("mark")
        rect = self.pixel_rect() if rect is None else rect
        if not rect:
            return
        x0, y0, x1, y1 = rect
        w, h = round(x1 - x0), round(y1 - y0)
        if not self.drag and w > 1 and h > 1:
            ts = date_label(datetime.now().astimezone().strftime("%Y.%m.%d %H:%M:%S %z"))
            pdf = stamp_pdf(w, h, self.signer_name(), ts)
            with PDFIUM_LOCK, pdfium.PdfDocument(pdf) as doc, closing(doc[0]) as pg:
                with closing(pg.render(fill_color=(255, 255, 255, 0))) as bmp:
                    self.art_photo = ImageTk.PhotoImage(bmp.to_pil().convert("RGBA"))
            c.create_image(
                self.ox + x0, self.oy + y0, anchor="nw", image=self.art_photo, tags="mark"
            )
        x0, x1, y0, y1 = x0 + self.ox, x1 + self.ox, y0 + self.oy, y1 + self.oy
        c.create_rectangle(x0, y0, x1, y1, outline="#1166b7", width=2, tags="mark")
        for x in (x0, x1):
            for y in (y0, y1):
                c.create_rectangle(
                    x - 3, y - 3, x + 3, y + 3, fill="white", outline="#1166b7", tags="mark"
                )

    def point(self, event):
        return self.canvas.canvasx(event.x) - self.ox, self.canvas.canvasy(event.y) - self.oy

    def press(self, event):
        if not self.view:
            return
        x, y = self.point(event)
        w, h = self.view.image.size
        if not (0 <= x <= w and 0 <= y <= h):
            return
        rect = self.pixel_rect()
        if rect:
            x0, y0, x1, y1 = rect
            for cx, other_x in ((x0, x1), (x1, x0)):
                for cy, other_y in ((y0, y1), (y1, y0)):
                    if abs(x - cx) <= 7 and abs(y - cy) <= 7:
                        self.drag = ("draw", other_x, other_y, rect)
                        return
            if x0 < x < x1 and y0 < y < y1:
                self.drag = ("move", x, y, rect)
                return
        self.drag = ("draw", x, y, None)

    def drag_rect(self, event):
        mode, x0, y0, old = self.drag
        x, y = self.point(event)
        w, h = self.view.image.size
        if mode == "draw":
            return ordered(x0, y0, min(w, max(0, x)), min(h, max(0, y)))
        l, t, r, b = old
        dx, dy = min(w - r, max(-l, x - x0)), min(h - b, max(-t, y - y0))
        return l + dx, t + dy, r + dx, b + dy

    def motion(self, event):
        if self.drag:
            self.paint_mark(self.drag_rect(event))

    def release(self, event):
        if not self.drag:
            return
        l, t, r, b = self.drag_rect(event)
        self.drag = None
        rect = ordered(*self.view.to_page(l, t), *self.view.to_page(r, b))
        if min(r - l, b - t) >= 6 and min(rect[2] - rect[0], rect[3] - rect[1]) >= 4:
            self.marks[self.path] = MarkedBox(
                self.path, self.view.revision, self.page_index, rect, self.view.rotation
            )
            self.show_mark = True
            self.on_mark()
        self.paint_mark()
