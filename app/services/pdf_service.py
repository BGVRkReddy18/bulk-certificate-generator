"""
AEREO Bulk Certificate Generator — PDF generation service.

Uses ReportLab to render a single professional certificate template.
"""

import logging
import re
import uuid
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import inch, mm
from reportlab.pdfgen.canvas import Canvas

logger = logging.getLogger(__name__)


def _sanitize_filename(name: str) -> str:
    """Strip non-alphanumeric characters to produce a safe filename component."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:80]


def generate_certificate_pdf(
    *,
    recipient_name: str,
    event_name: str,
    issue_date: str,
    certificate_id: str,
    output_dir: Path,
) -> Path:
    """
    Render a professional certificate PDF and return its path.

    Raises on I/O or rendering errors — callers must handle exceptions.
    """
    safe_name = _sanitize_filename(recipient_name)
    filename = f"{certificate_id}_{safe_name}.pdf"
    filepath = output_dir / filename

    width, height = landscape(A4)
    c = Canvas(str(filepath), pagesize=landscape(A4))

    # ── Background ──────────────────────────────────────────────────────
    c.setFillColor(HexColor("#FFFDF7"))
    c.rect(0, 0, width, height, fill=True, stroke=False)

    # ── Decorative border ───────────────────────────────────────────────
    border_color = HexColor("#1B3A5C")
    c.setStrokeColor(border_color)
    c.setLineWidth(3)
    margin = 25 * mm
    c.rect(margin, margin, width - 2 * margin, height - 2 * margin)

    # Inner thin border
    c.setLineWidth(0.75)
    inner = margin + 4 * mm
    c.rect(inner, inner, width - 2 * inner, height - 2 * inner)

    # ── Gold accent line ────────────────────────────────────────────────
    gold = HexColor("#C9A84C")
    c.setStrokeColor(gold)
    c.setLineWidth(1.5)
    accent_y = height - margin - 30 * mm
    c.line(margin + 40 * mm, accent_y, width - margin - 40 * mm, accent_y)

    # ── Title ───────────────────────────────────────────────────────────
    c.setFillColor(border_color)
    c.setFont("Helvetica", 14)
    c.drawCentredString(width / 2, height - margin - 20 * mm, "AEREO ACADEMY")

    c.setFont("Helvetica-Bold", 32)
    c.drawCentredString(width / 2, height - margin - 45 * mm, "Certificate of Completion")

    # ── Recipient name ──────────────────────────────────────────────────
    c.setFont("Helvetica", 13)
    c.setFillColor(HexColor("#333333"))
    c.drawCentredString(width / 2, height / 2 + 18 * mm, "This is proudly presented to")

    c.setFont("Helvetica-Bold", 28)
    c.setFillColor(border_color)
    c.drawCentredString(width / 2, height / 2 + 4 * mm, recipient_name)

    # Underline below name
    name_width = c.stringWidth(recipient_name, "Helvetica-Bold", 28)
    c.setStrokeColor(gold)
    c.setLineWidth(1)
    c.line(
        width / 2 - name_width / 2,
        height / 2 + 1 * mm,
        width / 2 + name_width / 2,
        height / 2 + 1 * mm,
    )

    # ── Event / course ──────────────────────────────────────────────────
    c.setFont("Helvetica", 13)
    c.setFillColor(HexColor("#333333"))
    c.drawCentredString(width / 2, height / 2 - 12 * mm, "for successfully completing")

    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(border_color)
    c.drawCentredString(width / 2, height / 2 - 24 * mm, event_name)

    # ── Date and certificate ID ─────────────────────────────────────────
    c.setFont("Helvetica", 11)
    c.setFillColor(HexColor("#555555"))
    c.drawCentredString(width / 2, margin + 28 * mm, f"Date of Issue: {issue_date}")

    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor("#888888"))
    c.drawCentredString(width / 2, margin + 20 * mm, f"Certificate ID: {certificate_id}")

    # ── Bottom gold accent ──────────────────────────────────────────────
    c.setStrokeColor(gold)
    c.setLineWidth(1.5)
    c.line(margin + 40 * mm, margin + 15 * mm, width - margin - 40 * mm, margin + 15 * mm)

    c.save()
    logger.info("Generated certificate: %s", filepath)
    return filepath
