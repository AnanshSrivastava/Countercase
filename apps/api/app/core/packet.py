"""The evidence packet PDF (F5): the letter, a source index that prints each system record verbatim
next to the claim it backs, and the seller's own attachments, clearly labelled as seller-provided.

A bank reviewer can compare any claim with its source on the page. Seller-provided files are
never described as verified. Images are embedded; PDFs are appended; anything that cannot be
read is listed as not embedded instead of failing the approval.
"""

import io
from dataclasses import dataclass, field

from fpdf import FPDF
from pypdf import PdfReader, PdfWriter

from app.core.models import Claim
from app.core.money import format_money
from app.core.tables import DisputeRow, EvidenceRow

# Stripe: combined evidence files at most 4.5 MB. Stay under it.
MAX_PACKET_BYTES = 4_400_000

TRANSLITERATE = {
    "₹": "Rs ",
    "€": "EUR ",
    "£": "GBP ",
    "—": "-",
    "–": "-",
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "…": "...",
    " ": " ",
}


class PacketTooLarge(Exception):
    pass


@dataclass
class Attachment:
    name: str  # display name shown in the packet
    data: bytes
    kind: str  # png | jpg | pdf


@dataclass
class PacketResult:
    pdf: bytes
    pages: int
    embedded: list[str] = field(default_factory=list)
    not_embedded: list[str] = field(default_factory=list)


def pdf_safe(text: str) -> str:
    """Built-in PDF fonts are Latin-1 only: transliterate common symbols, replace the rest."""
    for src, dst in TRANSLITERATE.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", "replace").decode("latin-1")


def _write(pdf: FPDF, text: str, *, size: int = 11, bold: bool = False, gap: float = 1.5) -> None:
    pdf.set_font("Helvetica", "B" if bold else "", size)
    pdf.multi_cell(0, 5.5, pdf_safe(text), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(gap)


def build_packet(
    *,
    dispute: DisputeRow,
    letter_md: str,
    claims: list[Claim],
    evidence: dict[str, EvidenceRow],
    attachments: list[Attachment],
) -> PacketResult:
    readable_pdfs: dict[int, PdfReader] = {}
    embedded: list[str] = []
    not_embedded: list[str] = []
    for i, att in enumerate(attachments):
        if att.kind == "pdf":
            try:
                readable_pdfs[i] = PdfReader(io.BytesIO(att.data))
                len(readable_pdfs[i].pages)
            except Exception:
                readable_pdfs.pop(i, None)

    pdf = FPDF()
    pdf.set_auto_page_break(True, margin=15)
    pdf.set_title("Response to payment dispute")
    pdf.add_page()

    _write(pdf, "Response to payment dispute", size=16, bold=True, gap=3)
    _write(
        pdf,
        f"Dispute {dispute.processor_dispute_id} ({dispute.processor})\n"
        f"Amount: {format_money(dispute.amount, dispute.currency)}\n"
        f"Reason code: {dispute.reason_raw}\n"
        f"Response due: {dispute.deadline_at.strftime('%Y-%m-%d %H:%M UTC')}",
        gap=4,
    )
    _write(pdf, letter_md, gap=5)

    _write(pdf, "Source index", size=13, bold=True, gap=2)
    _write(
        pdf,
        "Each statement above is backed by a record from the seller's own systems. "
        "The record is reproduced word for word so it can be compared with the statement.",
    )
    numbered = list(dict.fromkeys(c.evidence_id for c in claims))
    for n, ev_id in enumerate(numbered, start=1):
        ev = evidence[ev_id]
        _write(
            pdf,
            f"[{n}] {ev_id} - {ev.type.replace('_', ' ')} from {ev.source}, "
            f"recorded {ev.captured_at.strftime('%Y-%m-%d %H:%M UTC')} (verified record)\n"
            f"{ev.summary}",
            size=10,
        )

    divider_pages: list[int] = []  # zero-based page index where each attachment starts
    for i, att in enumerate(attachments):
        label = f"Attachment {i + 1}: {att.name}"
        pdf.add_page()
        divider_pages.append(pdf.page - 1)
        _write(pdf, label, size=13, bold=True, gap=1)
        _write(
            pdf,
            "Provided by the seller. Not independently verified by the system.",
            size=10,
        )
        if att.kind in ("png", "jpg"):
            try:
                pdf.image(io.BytesIO(att.data), w=min(170, pdf.epw))
                embedded.append(att.name)
            except Exception:
                _write(pdf, "This image could not be embedded.", size=10)
                not_embedded.append(att.name)
        elif i in readable_pdfs:
            _write(pdf, "The pages of this file follow this page.", size=10)
            embedded.append(att.name)
        else:
            _write(pdf, "This PDF could not be read and is not included.", size=10)
            not_embedded.append(att.name)

    main = bytes(pdf.output())
    if not readable_pdfs:
        merged = main
        pages = len(PdfReader(io.BytesIO(main)).pages)
    else:
        writer = PdfWriter()
        reader = PdfReader(io.BytesIO(main))
        # An image can add pages after its divider, so insert each attached PDF right before the
        # next attachment's divider (or at the end), not right after its own.
        insert_before = {
            divider_pages[i + 1] if i + 1 < len(divider_pages) else None: i
            for i in range(len(divider_pages))
        }
        for page_no, page in enumerate(reader.pages):
            if page_no in insert_before and insert_before[page_no] in readable_pdfs:
                for extra in readable_pdfs[insert_before[page_no]].pages:
                    writer.add_page(extra)
            writer.add_page(page)
        if None in insert_before and insert_before[None] in readable_pdfs:
            for extra in readable_pdfs[insert_before[None]].pages:
                writer.add_page(extra)
        buf = io.BytesIO()
        writer.write(buf)
        merged = buf.getvalue()
        pages = len(PdfReader(io.BytesIO(merged)).pages)

    if len(merged) > MAX_PACKET_BYTES:
        raise PacketTooLarge(
            f"the packet is {len(merged) / 1_000_000:.1f} MB; Stripe accepts at most 4.5 MB "
            "of evidence files in total. Remove an attachment and try again."
        )
    return PacketResult(pdf=merged, pages=pages, embedded=embedded, not_embedded=not_embedded)
