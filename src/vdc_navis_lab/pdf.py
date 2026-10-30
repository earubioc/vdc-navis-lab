"""A small PDF writer with no dependencies: A4, the two standard Helvetica fonts, text, rectangles and page numbers.

Only what the coordination report needs. Text is encoded as Windows-1252 (Spanish accents work), anything else prints as ?.
"""

from __future__ import annotations

# glyph advance widths (1/1000 em) for code points 32..255 in cp1252, from the Adobe Helvetica metrics
_W_REGULAR = (
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556,
    556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667,
    556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556,
    556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722,
    500, 500, 500, 334, 260, 334, 584, 761, 556, 761, 222, 556, 333, 1000, 556, 556, 333, 1000, 667, 333, 1000,
    761, 611, 761, 761, 222, 222, 333, 333, 350, 556, 1000, 333, 1000, 500, 333, 944, 761, 500, 667, 278, 333,
    556, 556, 556, 556, 260, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333, 333, 556, 537, 278,
    333, 333, 365, 556, 834, 834, 834, 611, 667, 667, 667, 667, 667, 667, 1000, 722, 667, 667, 667, 667, 278, 278,
    278, 278, 722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667, 611, 556, 556, 556, 556,
    556, 556, 889, 500, 556, 556, 556, 556, 278, 278, 278, 278, 556, 556, 556, 556, 556, 556, 556, 584, 611, 556,
    556, 556, 556, 500, 556, 500
)
_W_BOLD = (
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556,
    556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722,
    611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556, 333, 556,
    611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778,
    556, 556, 500, 389, 280, 389, 584, 761, 556, 761, 278, 556, 500, 1000, 556, 556, 333, 1000, 667, 333, 1000,
    761, 611, 761, 761, 278, 278, 500, 500, 350, 556, 1000, 333, 1000, 556, 333, 944, 761, 500, 667, 278, 333,
    556, 556, 556, 556, 280, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333, 333, 611, 556, 278,
    333, 333, 365, 556, 834, 834, 834, 611, 722, 722, 722, 722, 722, 722, 1000, 722, 667, 667, 667, 667, 278, 278,
    278, 278, 722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667, 611, 556, 556, 556, 556,
    556, 556, 889, 556, 556, 556, 556, 556, 278, 278, 278, 278, 611, 611, 611, 611, 611, 611, 611, 584, 611, 611,
    611, 611, 611, 556, 611, 556
)
PAGE_W, PAGE_H = 595.28, 841.89
MARGIN = 48.0

Color = tuple[float, float, float]
INK: Color = (0.10, 0.11, 0.13)
MUTED: Color = (0.42, 0.45, 0.50)
RULE: Color = (0.82, 0.84, 0.87)


def _hex(h: str) -> Color:
    return (int(h[1:3], 16) / 255, int(h[3:5], 16) / 255, int(h[5:7], 16) / 255)


def width(text: str, size: float, bold: bool = False) -> float:
    table = _W_BOLD if bold else _W_REGULAR
    total = 0
    for ch in text:
        try:
            code = ch.encode("cp1252")[0]
        except (UnicodeEncodeError, IndexError):
            code = 63
        total += table[code - 32] if 32 <= code <= 255 else 0
    return total * size / 1000


def wrap(text: str, size: float, max_w: float, bold: bool = False) -> list[str]:
    lines: list[str] = []
    for para in str(text).split("\n"):
        cur = ""
        for word in para.split(" "):
            trial = word if not cur else cur + " " + word
            if width(trial, size, bold) <= max_w or not cur:
                cur = trial
                while width(cur, size, bold) > max_w and len(cur) > 1:  # a single word longer than the line
                    cut = len(cur)
                    while cut > 1 and width(cur[:cut], size, bold) > max_w:
                        cut -= 1
                    lines.append(cur[:cut])
                    cur = cur[cut:]
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def _esc(s: str) -> bytes:
    b = s.encode("cp1252", errors="replace")
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


class Document:
    """Flow layout on A4: a cursor moves down the page and a new page starts when the next block does not fit."""

    def __init__(self, title: str = "", footer: str = "") -> None:
        self.title, self.footer = title, footer
        self.pages: list[list[bytes]] = []
        self.y = 0.0
        self._new_page()

    # -- low level
    def _new_page(self) -> None:
        self.pages.append([])
        self.y = PAGE_H - MARGIN

    def _out(self, s: str | bytes) -> None:
        self.pages[-1].append(s.encode("latin-1") if isinstance(s, str) else s)

    @staticmethod
    def _rgb(c: Color) -> str:
        return f"{c[0]:.3f} {c[1]:.3f} {c[2]:.3f}"

    def rect(self, x: float, y: float, w: float, h: float, fill: Color) -> None:
        self._out(f"{self._rgb(fill)} rg {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f\n")

    def hline(self, y: float, color: Color = RULE, x0: float = MARGIN, x1: float = PAGE_W - MARGIN) -> None:
        self._out(f"{self._rgb(color)} RG 0.6 w {x0:.2f} {y:.2f} m {x1:.2f} {y:.2f} l S\n")

    def text_at(self, x: float, y: float, s: str, size: float = 9.5, bold: bool = False, color: Color = INK) -> None:
        font = "F2" if bold else "F1"
        self._out(f"BT {self._rgb(color)} rg /{font} {size:.1f} Tf {x:.2f} {y:.2f} Td (".encode("latin-1") + _esc(s) + b") Tj ET\n")

    def need(self, h: float) -> None:
        if self.y - h < MARGIN + 18:
            self._new_page()

    # -- blocks
    def gap(self, h: float) -> None:
        self.y -= h

    def heading(self, s: str, size: float = 13, color: Color = INK) -> None:
        self.need(size * 2.6)
        self.y -= size * 0.9
        self.text_at(MARGIN, self.y, s, size, True, color)
        self.y -= 4
        self.hline(self.y)
        self.y -= 8

    def paragraph(self, s: str, size: float = 9.5, bold: bool = False, color: Color = INK, indent: float = 0,
                  leading: float = 1.3, bullet: str = "") -> None:
        max_w = PAGE_W - 2 * MARGIN - indent - (10 if bullet else 0)
        lines = wrap(s, size, max_w, bold)
        for n, line in enumerate(lines):
            self.need(size * leading)
            self.y -= size * leading
            if bullet and n == 0:
                self.text_at(MARGIN + indent, self.y, bullet, size, True, MUTED)
            self.text_at(MARGIN + indent + (10 if bullet else 0), self.y, line, size, bold, color)

    def bar(self, parts: list[tuple[str, float, Color]], h: float = 16) -> None:
        """A stacked horizontal bar; each part is (label, value, colour)."""
        total = sum(v for _, v, _ in parts) or 1
        self.need(h + 22)
        self.y -= h
        x, w_all = MARGIN, PAGE_W - 2 * MARGIN
        for _, v, c in parts:
            if v <= 0:
                continue
            w = w_all * v / total
            self.rect(x, self.y, w, h, c)
            x += w
        self.y -= 4

    def legend(self, items: list[tuple[str, Color]]) -> None:
        self.need(14)
        self.y -= 10
        x = MARGIN
        for label, c in items:
            self.rect(x, self.y - 1, 8, 8, c)
            self.text_at(x + 12, self.y, label, 8.5, False, MUTED)
            x += 12 + width(label, 8.5) + 16
        self.y -= 4

    def table(self, header: list[str], rows: list[list[str]], widths: list[float], size: float = 8.5,
              chips: dict[int, dict[str, Color]] | None = None) -> None:
        """Columns are sized by weight (widths), text wraps inside the cell, the header repeats on every page.
        chips: column index -> {cell text: colour}; a coloured cell is drawn as a small badge."""
        total = sum(widths)
        avail = PAGE_W - 2 * MARGIN
        cols = [avail * w / total for w in widths]
        pad = 4.0

        def draw_header() -> None:
            self.need(size * 2.4)
            self.y -= size * 1.2
            self.rect(MARGIN, self.y - 4, avail, size * 1.2 + 6, (0.93, 0.94, 0.96))
            x = MARGIN
            for h, w in zip(header, cols):
                self.text_at(x + pad, self.y, h, size, True, MUTED)
                x += w
            self.y -= 6

        draw_header()
        for row in rows:
            cells = [wrap(str(v), size, w - 2 * pad) for v, w in zip(row, cols)]
            height = max(len(c) for c in cells) * size * 1.25 + 5
            if self.y - height < MARGIN + 18:
                self._new_page()
                draw_header()
            top = self.y
            x = MARGIN
            for ci, (lines, w) in enumerate(zip(cells, cols)):
                badge = (chips or {}).get(ci, {}).get(str(row[ci]))
                if badge is not None:
                    bw = min(w - 2 * pad + 2, width(str(row[ci]), size - 1, True) + 8)
                    self.rect(x + pad - 1, top - size - 1, bw, size + 3, badge)
                    self.text_at(x + pad + 3, top - size + 1.5, str(row[ci]), size - 1, True, (1, 1, 1))
                else:
                    for k, line in enumerate(lines):
                        self.text_at(x + pad, top - size - k * size * 1.25 + 1, line, size)
                x += w
            self.y = top - height
            self.hline(self.y + 2.5, (0.9, 0.91, 0.93))

    # -- output
    def render(self) -> bytes:
        objs: list[bytes] = []

        def add(body: bytes) -> int:
            objs.append(body)
            return len(objs)

        add(b"")  # 1: catalog (filled later)
        add(b"")  # 2: pages (filled later)
        f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        kids = []
        n_pages = len(self.pages)
        for n, parts in enumerate(self.pages, 1):
            body = b"".join(parts)
            foot = self.footer
            tail = (f"BT {self._rgb(MUTED)} rg /F1 8 Tf {MARGIN:.2f} {MARGIN - 14:.2f} Td (").encode("latin-1") + _esc(foot) + b") Tj ET\n"
            label = f"{n} / {n_pages}"
            tail += (f"BT {self._rgb(MUTED)} rg /F1 8 Tf {PAGE_W - MARGIN - width(label, 8):.2f} {MARGIN - 14:.2f} Td (").encode("latin-1") + _esc(label) + b") Tj ET\n"
            stream = body + tail
            c = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
            p = add(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W:.2f} {PAGE_H:.2f}] "
                    f"/Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >> >> /Contents {c} 0 R >>".encode("latin-1"))
            kids.append(p)
        objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
        objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode("latin-1")
        info = add(b"<< /Title (" + _esc(self.title) + b") /Producer (vdc-navis-lab) >>")
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, body in enumerate(objs, 1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
        for off in offsets:
            out += b"%010d 00000 n \n" % off
        out += b"trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, info, xref)
        return bytes(out)
