"""Renders a quote (application/read_models.py's QuoteDocumentRecord) as a
downloadable A4 PDF - the customer-facing offer, so it shows what the
customer is offered (route, cargo, price) but never the carrier or its cost.

Hand-written PDF 1.4 output using the built-in Helvetica fonts with
WinAnsiEncoding (covers å/ä/ö/é), so no PDF library has to be added to the
backend image. Only what a one/two-page offer needs: text, lines, filled
rectangles and automatic page breaks.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from qinora.application.read_models import QuoteDocumentRecord

SENDER_NAME = "Sandahls"
QUOTE_VALIDITY_DAYS = 7

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN = 50
BOTTOM = 70

_LINE_ITEM_LABELS_SV = {"freight charge": "Frakt"}
_DRAFT_STATUSES = {"draft", "pending", "pending_review"}

# Helvetica glyph widths (1/1000 em) for ASCII 32-126, from the standard AFM.
_HELVETICA_WIDTHS = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
]
_TEXT_REPLACEMENTS = str.maketrans({"→": "->", "−": "-", " ": " ", "\t": " "})


def render_quote_pdf(document: QuoteDocumentRecord) -> bytes:
    quote = document.quote
    request = document.request.request if document.request else None
    pdf = _PdfBuilder(title=f"Offert {quote_reference(document)}")

    # Header
    pdf.text(MARGIN, pdf.y, "OFFERT", size=24, bold=True)
    pdf.text_right(PAGE_WIDTH - MARGIN, pdf.y + 6, SENDER_NAME, size=13, bold=True)
    if quote.status in _DRAFT_STATUSES:
        pdf.text(MARGIN + 118, pdf.y + 4, "UTKAST - ej skickad", size=10, gray=0.45)
    pdf.y -= 36

    offer_date = _offer_date(document)
    meta = [
        ("Offertreferens", quote_reference(document)),
        ("Offertdatum", offer_date.isoformat()),
        ("Giltig till", (offer_date + timedelta(days=QUOTE_VALIDITY_DAYS)).isoformat()),
    ]
    top = pdf.y
    pdf.label(MARGIN, top, "Kund")
    pdf.text(MARGIN, top - 15, quote.customer or "-", size=12, bold=True)
    if document.sent_email:
        pdf.text(MARGIN, top - 30, document.sent_email.recipient, size=9, gray=0.35)
    for index, (label, value) in enumerate(meta):
        y = top - index * 26
        pdf.label(360, y, label)
        pdf.text(360, y - 12, value, size=10)
    pdf.y = top - 84
    pdf.rule()

    # Transport assignment
    pdf.section("Transportuppdrag")
    lane = quote.lane or (request.lane if request else None) or "-"
    rows = [("Rutt", lane.replace(" -> ", " – "))]
    if request is not None:
        rows.append(("Transportläge", request.mode.upper()))
        if request.weight_kg:
            rows.append(("Total vikt", f"{_number(request.weight_kg)} kg"))
    for label, value in rows:
        pdf.ensure_space(16)
        pdf.text(MARGIN, pdf.y, label, size=10, gray=0.35)
        pdf.text(170, pdf.y, value, size=10)
        pdf.y -= 16

    cargo = document.request.cargo_lines if document.request else ()
    if cargo:
        pdf.y -= 6
        columns = [(MARGIN, "Gods"), (300, "Antal"), (360, "Vikt (kg)"), (440, "Mått (cm)")]
        pdf.table_header(columns)
        for line in cargo:
            description = line.description
            if line.hazardous:
                un_number = f" (UN {line.un_number})" if line.un_number else ""
                description += f" - farligt gods{un_number}"
            wrapped = _wrap(description, 240, size=9)
            pdf.ensure_space(14 * len(wrapped))
            for offset, part in enumerate(wrapped):
                pdf.text(MARGIN, pdf.y - offset * 12, part, size=9)
            pdf.text(300, pdf.y, str(line.quantity) if line.quantity else "-", size=9)
            pdf.text(360, pdf.y, _number(line.weight_kg) if line.weight_kg else "-", size=9)
            pdf.text(440, pdf.y, _dimensions(line.length_cm, line.width_cm, line.height_cm), size=9)
            pdf.y -= 12 * len(wrapped) + 4
    pdf.y -= 10

    # Price
    pdf.section("Pris")
    pdf.table_header([(MARGIN, "Beskrivning")], right=[(PAGE_WIDTH - MARGIN, "Belopp")])
    for description, amount in _price_lines(document):
        pdf.ensure_space(16)
        pdf.text(MARGIN, pdf.y, description, size=10)
        pdf.text_right(PAGE_WIDTH - MARGIN, pdf.y, _money(amount, quote.currency), size=10)
        pdf.y -= 16
    pdf.y -= 8
    pdf.ensure_space(30)
    pdf.fill_rect(MARGIN, pdf.y - 8, PAGE_WIDTH - 2 * MARGIN, 24, gray=0.93)
    pdf.text(MARGIN + 8, pdf.y, "Totalt", size=11, bold=True)
    pdf.text_right(
        PAGE_WIDTH - MARGIN - 8, pdf.y, _money(quote.customer_price, quote.currency),
        size=11, bold=True,
    )
    pdf.y -= 40

    # Terms
    pdf.ensure_space(40)
    for part in _wrap(
        f"Offerten gäller i {QUOTE_VALIDITY_DAYS} dagar från offertdatum. "
        "Svara på vårt mail för att godkänna offerten, så bokar vi transporten.",
        PAGE_WIDTH - 2 * MARGIN,
        size=9,
    ):
        pdf.text(MARGIN, pdf.y, part, size=9, gray=0.35)
        pdf.y -= 12

    return pdf.build()


def quote_reference(document: QuoteDocumentRecord) -> str:
    quote = document.quote
    base = document.request.request.public_id if document.request else quote.id[:8].upper()
    return f"{base}-V{quote.version}"


def quote_filename(document: QuoteDocumentRecord) -> str:
    customer = "".join(
        char if char.isalnum() else "-" for char in (document.quote.customer or "offert")
    ).strip("-")
    return f"Offert-{quote_reference(document)}-{customer or 'kund'}.pdf"


def _price_lines(document: QuoteDocumentRecord) -> list[tuple[str, float]]:
    quote = document.quote
    items = document.line_items
    # Only itemise when the items actually add up to the quoted price (a
    # revised quote can carry a new total without re-itemising).
    if items and abs(sum(item.amount for item in items) - quote.customer_price) < 0.01:
        return [
            (_LINE_ITEM_LABELS_SV.get(item.description.lower(), item.description), item.amount)
            for item in items
        ]
    return [("Transport enligt ovan", quote.customer_price)]


def _offer_date(document: QuoteDocumentRecord) -> date:
    email = document.sent_email
    for value in (email.sent_at if email else None, email.created_at if email else None):
        if value:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
            except ValueError:
                continue
    return date.today()


def _money(amount: float, currency: str) -> str:
    formatted = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    return f"{formatted} {currency}"


def _number(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ") if value >= 1000 else f"{value:g}"


def _dimensions(*values: float | None) -> str:
    if not any(values):
        return "-"
    return " x ".join(_number(value) if value else "?" for value in values)


def _text_width(text: str, size: float) -> float:
    total = 0
    for char in _normalize(text):
        code = ord(char)
        total += _HELVETICA_WIDTHS[code - 32] if 32 <= code <= 126 else 556
    return total * size / 1000


def _wrap(text: str, max_width: float, *, size: float) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        current = ""
        for word in paragraph.split(" "):
            candidate = f"{current} {word}".strip()
            if current and _text_width(candidate, size) > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    return lines


def _normalize(text: str) -> str:
    return text.translate(_TEXT_REPLACEMENTS)


def _pdf_string(text: str) -> bytes:
    encoded = _normalize(text).encode("cp1252", errors="replace")
    return b"(" + encoded.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


class _PdfBuilder:
    def __init__(self, *, title: str) -> None:
        self._title = title
        self._pages: list[list[bytes]] = []
        self.y = 0.0
        self._new_page()

    def _new_page(self) -> None:
        self._pages.append([])
        self.y = PAGE_HEIGHT - MARGIN - 20

    @property
    def _ops(self) -> list[bytes]:
        return self._pages[-1]

    def ensure_space(self, height: float) -> None:
        if self.y - height < BOTTOM:
            self._new_page()

    def text(
        self, x: float, y: float, text: str, *, size: float, bold: bool = False, gray: float = 0
    ) -> None:
        font = b"/F2" if bold else b"/F1"
        self._ops.append(
            b"BT %.3f g %s %.1f Tf %.2f %.2f Td %s Tj ET"
            % (gray, font, size, x, y, _pdf_string(text))
        )

    def text_right(
        self,
        right: float,
        y: float,
        text: str,
        *,
        size: float,
        bold: bool = False,
        gray: float = 0,
    ) -> None:
        self.text(right - _text_width(text, size), y, text, size=size, bold=bold, gray=gray)

    def label(self, x: float, y: float, text: str) -> None:
        self.text(x, y, text.upper(), size=7.5, bold=True, gray=0.45)

    def rule(self) -> None:
        self._ops.append(
            b"0.8 G 0.6 w %.2f %.2f m %.2f %.2f l S"
            % (MARGIN, self.y, PAGE_WIDTH - MARGIN, self.y)
        )
        self.y -= 24

    def fill_rect(self, x: float, y: float, width: float, height: float, *, gray: float) -> None:
        self._ops.append(b"%.3f g %.2f %.2f %.2f %.2f re f" % (gray, x, y, width, height))

    def section(self, title: str) -> None:
        self.ensure_space(60)
        self.text(MARGIN, self.y, title, size=12, bold=True)
        self.y -= 20

    def table_header(
        self,
        columns: list[tuple[float, str]],
        right: list[tuple[float, str]] | None = None,
    ) -> None:
        self.ensure_space(40)
        for x, title in columns:
            self.label(x, self.y, title)
        for x, title in right or []:
            self.text_right(x, self.y, title.upper(), size=7.5, bold=True, gray=0.45)
        self.y -= 6
        self._ops.append(
            b"0.8 G 0.6 w %.2f %.2f m %.2f %.2f l S"
            % (MARGIN, self.y, PAGE_WIDTH - MARGIN, self.y)
        )
        self.y -= 14

    def build(self) -> bytes:
        page_count = len(self._pages)
        # Object layout: 1 catalog, 2 page tree, 3/4 fonts, 5 info, then a
        # (page, content stream) pair per page.
        page_ids = [6 + index * 2 for index in range(page_count)]
        objects: dict[int, bytes] = {
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            2: b"<< /Type /Pages /Kids [%s] /Count %d >>"
            % (b" ".join(b"%d 0 R" % page_id for page_id in page_ids), page_count),
            3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
            b"/Encoding /WinAnsiEncoding >>",
            4: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
            b"/Encoding /WinAnsiEncoding >>",
            5: b"<< /Title %s /Producer (QiNora) >>" % _pdf_string(self._title),
        }
        for index, ops in enumerate(self._pages):
            footer = b"BT 0.55 g /F1 7.5 Tf %.2f 30 Td %s Tj ET" % (
                MARGIN,
                _pdf_string(f"{SENDER_NAME} - sida {index + 1} av {page_count}"),
            )
            stream = b"\n".join([*ops, footer])
            page_id = page_ids[index]
            objects[page_id] = (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
                b"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents %d 0 R >>"
                % (PAGE_WIDTH, PAGE_HEIGHT, page_id + 1)
            )
            objects[page_id + 1] = (
                b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)
            )

        output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets: dict[int, int] = {}
        for object_id in sorted(objects):
            offsets[object_id] = len(output)
            output += b"%d 0 obj\n%s\nendobj\n" % (object_id, objects[object_id])
        xref_offset = len(output)
        size = max(objects) + 1
        output += b"xref\n0 %d\n0000000000 65535 f \n" % size
        for object_id in range(1, size):
            output += b"%010d 00000 n \n" % offsets[object_id]
        output += b"trailer\n<< /Size %d /Root 1 0 R /Info 5 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
            size,
            xref_offset,
        )
        return bytes(output)
