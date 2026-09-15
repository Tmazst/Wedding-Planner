from html import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


PLUM = colors.HexColor("#6f294d")
INK = colors.HexColor("#28222a")
MUTED = colors.HexColor("#746c74")
ROSE = colors.HexColor("#f4e5eb")
LINE = colors.HexColor("#e8dfe2")


def _money(value):
    return f"E{value or 0:,.2f}"


def _text(value, style):
    return Paragraph(escape(str(value or "")), style)


def _footer(canvas, document):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 9.5 * mm, "UMSHADO Wedding Planner")
    canvas.drawRightString(A4[0] - 18 * mm, 9.5 * mm, f"Page {document.page}")
    canvas.restoreState()


def build_wedding_report(stream, *, wedding, planned_total, selected_total, remaining, members, generated_at):
    document = SimpleDocTemplate(
        stream,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
        title=f"{wedding.title} Wedding Report",
        author="UMSHADO Wedding Planner",
    )
    sample = getSampleStyleSheet()
    title = ParagraphStyle(
        "ReportTitle", parent=sample["Title"], fontName="Helvetica-Bold",
        fontSize=25, leading=30, textColor=PLUM, alignment=TA_CENTER, spaceAfter=5 * mm,
    )
    subtitle = ParagraphStyle(
        "Subtitle", parent=sample["Normal"], fontSize=10, leading=15,
        textColor=MUTED, alignment=TA_CENTER, spaceAfter=8 * mm,
    )
    heading = ParagraphStyle(
        "Heading", parent=sample["Heading2"], fontName="Helvetica-Bold",
        fontSize=13, leading=17, textColor=PLUM, spaceBefore=7 * mm, spaceAfter=3 * mm,
    )
    body = ParagraphStyle("Body", parent=sample["BodyText"], fontSize=9, leading=13, textColor=INK)
    small = ParagraphStyle("Small", parent=body, fontSize=8, leading=11, textColor=MUTED)
    right = ParagraphStyle("Right", parent=body, alignment=TA_RIGHT)

    date_text = wedding.wedding_date.strftime("%d %B %Y") if wedding.wedding_date else "Date not set"
    location_text = wedding.location or "Location not set"
    story = [
        Paragraph("WEDDING PLAN", subtitle),
        _text(wedding.title, title),
        Paragraph(f"{escape(date_text)} &nbsp;&nbsp; | &nbsp;&nbsp; {escape(location_text)}", subtitle),
    ]

    summary_data = [
        [Paragraph("TOTAL BUDGET", small), Paragraph("PLANNED ITEMS", small), Paragraph("SELECTED QUOTES", small), Paragraph("REMAINING", small)],
        [_money(wedding.budget_target), _money(planned_total), _money(selected_total), _money(remaining)],
    ]
    summary = Table(summary_data, colWidths=[(A4[0] - 36 * mm) / 4] * 4)
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ROSE),
        ("TEXTCOLOR", (0, 1), (-1, 1), PLUM),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, 1), 11),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), .7, LINE),
        ("INNERGRID", (0, 0), (-1, -1), .4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.extend([summary, Paragraph("Budget and selected vendors", heading)])

    budget_rows = [["Item", "Planned", "Selected vendor", "Selected amount", "Status"]]
    for category in wedding.categories:
        quote = category.selected_quote
        budget_rows.append([
            _text(category.name, body),
            Paragraph(_money(category.planned_amount), right),
            _text(quote.vendor_name if quote else "—", body),
            Paragraph(_money(quote.amount) if quote else "—", right),
            Paragraph("Confirmed" if quote else "Decision pending", body),
        ])
    if len(budget_rows) == 1:
        budget_rows.append([Paragraph("No budget items have been added.", body), "", "", "", ""])

    budget_table = Table(budget_rows, colWidths=[38 * mm, 28 * mm, 43 * mm, 30 * mm, 30 * mm], repeatRows=1)
    budget_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PLUM),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("GRID", (0, 0), (-1, -1), .4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fbf8f5")]),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(budget_table)

    selected_quotes = [category.selected_quote for category in wedding.categories if category.selected_quote]
    if selected_quotes:
        story.append(Paragraph("Vendor contacts and notes", heading))
        for quote in selected_quotes:
            details = [f"<b>{escape(quote.category.name)}: {escape(quote.vendor_name)}</b>"]
            if quote.contact:
                details.append(f"Contact: {escape(quote.contact)}")
            if quote.notes:
                details.append(escape(quote.notes))
            story.append(KeepTogether([Paragraph("<br/>".join(details), body), Spacer(1, 2.5 * mm)]))

    story.append(Paragraph("Planning team", heading))
    team_rows = [["Name", "Responsibility", "Email"]]
    team_rows.extend([
        [_text(member["name"], body), _text(member["role"], body), _text(member["email"], body)]
        for member in members
    ])
    team_table = Table(team_rows, colWidths=[48 * mm, 52 * mm, 69 * mm], repeatRows=1)
    team_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PLUM),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("GRID", (0, 0), (-1, -1), .4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([
        team_table,
        Spacer(1, 8 * mm),
        Paragraph(f"Report generated {generated_at.strftime('%d %B %Y at %H:%M UTC')}", small),
    ])
    document.build(story, onFirstPage=_footer, onLaterPages=_footer)
