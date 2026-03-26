import io
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .chart_generator import generate_plc_graph_images


PDF_HEADER_BG = HexColor("#2E5E9E")
PDF_GRID = HexColor("#B0B7C3")
LETTERHEAD_PRIMARY = HexColor("#123B67")
LETTERHEAD_SECONDARY = HexColor("#EAF1FB")
LETTERHEAD_TEXT_DARK = HexColor("#17324F")
PDF_PAGE_SIZE = A4
PDF_LEFT_RIGHT_MARGIN = 30
PDF_TOP_MARGIN = 96
PDF_BOTTOM_MARGIN = 36
try:
    IST_TIMEZONE = ZoneInfo("Asia/Kolkata")
except ZoneInfoNotFoundError:
    IST_TIMEZONE = timezone(timedelta(hours=5, minutes=30), name="IST")


def _safe_cell(value) -> str:
    if value is None:
        return ""
    return escape(str(value)).replace("\n", "<br/>")


def _normalize_rows(rows: list) -> list[list]:
    normalized: list[list] = []
    for row in rows or []:
        if isinstance(row, (list, tuple)):
            normalized.append(list(row))
        else:
            normalized.append([row])
    return normalized


def _column_widths(headers: list, rows: list[list], available_width: float) -> list[float]:
    num_cols = max(len(headers), 1)
    weights: list[float] = []
    sample_rows = rows[:200]

    for col in range(num_cols):
        lengths: list[int] = []
        if col < len(headers):
            lengths.append(len(str(headers[col])))
        for row in sample_rows:
            if col < len(row):
                lengths.append(len(str(row[col] if row[col] is not None else "")))
        max_len = max(lengths) if lengths else 8
        # Keep columns balanced in portrait mode so no single field dominates width.
        weights.append(float(min(max(max_len, 6), 26)))

    total_weight = sum(weights) or float(num_cols)
    return [available_width * (w / total_weight) for w in weights]


def _pdf_doc(buffer: io.BytesIO) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        buffer,
        pagesize=PDF_PAGE_SIZE,
        rightMargin=PDF_LEFT_RIGHT_MARGIN,
        leftMargin=PDF_LEFT_RIGHT_MARGIN,
        topMargin=PDF_TOP_MARGIN,
        bottomMargin=PDF_BOTTOM_MARGIN,
    )


def _table_font_sizes(num_cols: int) -> tuple[float, float]:
    if num_cols <= 5:
        return 9.0, 8.5
    if num_cols <= 8:
        return 8.5, 8.0
    if num_cols <= 11:
        return 8.0, 7.4
    return 7.6, 7.0


def _report_company_name() -> str:
    fallback = "SERKAYON FEED MILL"
    try:
        from ..config import get_settings

        name = (get_settings().app_name or "").strip()
        if name.endswith(" API"):
            name = name[:-4].strip()
        return name or fallback
    except Exception:
        return fallback


def _generated_at_text() -> str:
    return datetime.now(IST_TIMEZONE).strftime("%d %b %Y %I:%M %p")


def _format_timestamp_ist(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        utc_value = value.replace(tzinfo=timezone.utc)
    else:
        utc_value = value.astimezone(timezone.utc)
    return utc_value.astimezone(IST_TIMEZONE).strftime("%d %b %Y %I:%M:%S %p IST")


def _page_decorator(title: str, company_name: str, generated_at: str):
    report_title = str(title or "Report")[:120]

    def _draw(canvas, doc):
        page_width, page_height = doc.pagesize

        primary_h = 42
        secondary_h = 24

        canvas.saveState()

        canvas.setFillColor(LETTERHEAD_PRIMARY)
        canvas.rect(0, page_height - primary_h, page_width, primary_h, stroke=0, fill=1)

        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 13)
        canvas.drawString(doc.leftMargin, page_height - 26, company_name)

        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(
            page_width - doc.rightMargin,
            page_height - 16,
            f"Generated: {generated_at}",
        )

        canvas.setFillColor(LETTERHEAD_SECONDARY)
        secondary_y = page_height - primary_h - secondary_h
        canvas.rect(0, secondary_y, page_width, secondary_h, stroke=0, fill=1)

        canvas.setFillColor(LETTERHEAD_TEXT_DARK)
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawCentredString(page_width / 2.0, secondary_y + 8, report_title)

        footer_y = doc.bottomMargin - 12
        canvas.setStrokeColor(PDF_GRID)
        canvas.setLineWidth(0.6)
        canvas.line(doc.leftMargin, footer_y + 8, page_width - doc.rightMargin, footer_y + 8)

        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(HexColor("#64748B"))
        canvas.drawRightString(
            page_width - doc.rightMargin,
            footer_y,
            f"Page {canvas.getPageNumber()}",
        )

        canvas.restoreState()

    return _draw


def _build_data_table(
    headers: list,
    rows: list[list],
    doc_width: float,
    styles,
    target_height: float | None = None,
) -> Table:
    num_cols = len(headers) if headers else max((len(r) for r in rows), default=1)
    header_size, cell_size = _table_font_sizes(num_cols)

    header_style = ParagraphStyle(
        name="TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=header_size,
        leading=header_size + 2,
        textColor=colors.whitesmoke,
        alignment=TA_CENTER,
        wordWrap="CJK",
    )
    cell_style = ParagraphStyle(
        name="TableCell",
        parent=styles["Normal"],
        fontSize=cell_size,
        leading=cell_size + 2.5,
        wordWrap="CJK",
    )

    if not headers:
        headers = [f"Column {i + 1}" for i in range(num_cols)]

    table_data = [
        [Paragraph(_safe_cell(col), header_style) for col in headers],
        *[
            [
                Paragraph(_safe_cell(row[idx] if idx < len(row) else ""), cell_style)
                for idx in range(num_cols)
            ]
            for row in rows
        ],
    ]

    row_heights = None
    if target_height and target_height > 0:
        per_row = max(14.0, float(target_height) / max(len(table_data), 1))
        row_heights = [per_row] * len(table_data)

    table = Table(
        table_data,
        repeatRows=1,
        splitByRow=1,
        colWidths=_column_widths(headers, rows, doc_width),
        rowHeights=row_heights,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PDF_HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("WORDWRAP", (0, 0), (-1, -1), "CJK"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#F5FAFC"), HexColor("#FFFFFF")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, PDF_GRID),
                ("BOX", (0, 0), (-1, -1), 0.8, PDF_GRID),
            ]
        )
    )
    table.hAlign = "LEFT"
    return table


def export_table_to_pdf(title: str, headers: list, rows: list) -> bytes:
    buffer = io.BytesIO()
    generated_at = _generated_at_text()
    company_name = _report_company_name()

    doc = _pdf_doc(buffer)
    styles = getSampleStyleSheet()

    normalized_rows = _normalize_rows(rows)
    table = _build_data_table(headers, normalized_rows, doc.width, styles)

    intro_style = ParagraphStyle(
        name="Intro",
        parent=styles["Normal"],
        fontSize=8.5,
        textColor=HexColor("#475569"),
    )

    story = [
        Paragraph(
            f"Prepared on {generated_at} | Total Records: {len(normalized_rows)}",
            intro_style,
        ),
        Spacer(1, 7),
        table,
    ]

    decorator = _page_decorator(title, company_name, generated_at)
    doc.build(story, onFirstPage=decorator, onLaterPages=decorator)
    buffer.seek(0)
    return buffer.read()


def export_multi_table_to_pdf(title: str, sections: list[dict]) -> bytes:
    buffer = io.BytesIO()
    generated_at = _generated_at_text()
    company_name = _report_company_name()

    doc = _pdf_doc(buffer)
    styles = getSampleStyleSheet()
    section_style = ParagraphStyle(
        name="SectionTitle",
        parent=styles["Heading3"],
        textColor=HexColor("#123B67"),
    )
    intro_style = ParagraphStyle(
        name="IntroMulti",
        parent=styles["Normal"],
        fontSize=8.5,
        textColor=HexColor("#475569"),
    )

    story = [
        Paragraph(f"Prepared on {generated_at}", intro_style),
        Spacer(1, 8),
    ]

    for section in sections or []:
        section_title = section.get("title") or "Section"
        headers = section.get("headers") or []
        rows = _normalize_rows(section.get("rows") or [])
        if not rows:
            rows = [["No data available"]]
            if not headers:
                headers = ["Data"]

        story.append(Paragraph(_safe_cell(section_title), section_style))
        story.append(Spacer(1, 4))
        story.append(_build_data_table(headers, rows, doc.width, styles))
        story.append(Spacer(1, 8))

    decorator = _page_decorator(title, company_name, generated_at)
    doc.build(story, onFirstPage=decorator, onLaterPages=decorator)
    buffer.seek(0)
    return buffer.read()


def export_table_to_excel(title: str, headers: list, rows: list, sheet_name: str = "Sheet1") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]
    ws.append([title])
    ws.append([])
    ws.append(headers)
    for row in rows:
        ws.append(list(row))
    for cell in ws[3]:
        cell.font = Font(bold=True)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()


def export_multi_table_to_excel(title: str, sections: list[dict]) -> bytes:
    wb = Workbook()
    if not sections:
        sections = [{"title": "Data", "headers": ["Data"], "rows": []}]

    for idx, section in enumerate(sections):
        ws = wb.active if idx == 0 else wb.create_sheet()
        ws.title = str(section.get("sheet_name") or section.get("title") or f"Sheet{idx + 1}")[:31]
        headers = section.get("headers") or []
        rows = _normalize_rows(section.get("rows") or [])

        ws.append([title])
        ws.append([str(section.get("title") or "Section")])
        ws.append([])
        ws.append(headers or ["Data"])
        for row in rows:
            ws.append(list(row))

        for cell in ws[4]:
            cell.font = Font(bold=True)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()


def export_table_to_csv(headers: list, rows: list) -> str:
    import csv

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue()


def export_batch_report_pdf(
    batch,
    report,
    materials,
    plc_rows: list | None = None,
    plc_start: datetime | None = None,
    plc_end: datetime | None = None,
):
    buffer = io.BytesIO()
    generated_at = _generated_at_text()
    company_name = _report_company_name()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=96,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    story = []
    batch_start = plc_start or getattr(batch, "hmi_started_at", None)
    batch_end = plc_end or getattr(batch, "hmi_completed_at", None)

    panel_title_style = ParagraphStyle(
        name="PanelTitle",
        parent=styles["Normal"],
        fontSize=9,
        fontName="Helvetica-Bold",
        textColor=colors.white,
        alignment=TA_CENTER,
    )
    summary_cell_style = ParagraphStyle(
        name="SummaryCell",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=11,
        textColor=HexColor("#1E293B"),
    )

    def _display_value(value) -> str:
        if value in (None, ""):
            return "-"
        if isinstance(value, float):
            text = f"{value:.3f}".rstrip("0").rstrip(".")
            return text if text else "0"
        return str(value)

    def _date_text(value) -> str:
        if value is None:
            return "-"
        if isinstance(value, datetime):
            if value.tzinfo is None:
                utc_value = value.replace(tzinfo=timezone.utc)
            else:
                utc_value = value.astimezone(timezone.utc)
            return utc_value.astimezone(IST_TIMEZONE).strftime("%d %b %Y")
        return str(value)

    def panel(title: str, content: Table, width: float) -> Table:
        box = Table([[Paragraph(_safe_cell(title), panel_title_style)], [content]], colWidths=[width])
        box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, 0), PDF_HEADER_BG),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOX", (0, 0), (-1, -1), 0.6, PDF_GRID),
                    ("BOTTOMPADDING", (0, 0), (0, 0), 6),
                    ("TOPPADDING", (0, 0), (0, 0), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        return box

    story.append(Spacer(1, 2))

    batch_summary = [
        ("Batch ID", batch.id),
        ("Date", _date_text(batch.date)),
        ("Product", batch.product_name),
        ("Batch Size", batch.batch_size),
        ("Output", batch.output),
        ("Start Time", _format_timestamp_ist(batch_start)),
        ("End Time", _format_timestamp_ist(batch_end)),
        ("No. of Bags", getattr(batch, "num_bags", "") or ""),
        ("Weight/Bag", getattr(batch, "weight_per_bag", "") or ""),
        ("Water", batch.water if hasattr(batch, "water") else ""),
    ]
    summary_cells = [
        Paragraph(f"<b>{_safe_cell(label)}</b><br/>{_safe_cell(_display_value(value))}", summary_cell_style)
        for label, value in batch_summary
    ]
    summary_table = Table(
        [summary_cells[:5], summary_cells[5:10]],
        colWidths=[doc.width / 5.0] * 5,
        rowHeights=[56, 56],
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, -1), HexColor("#F8FBFF")),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [HexColor("#F8FBFF"), colors.white]),
                ("BOX", (0, 0), (-1, -1), 0.6, PDF_GRID),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, PDF_GRID),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(panel("Batch Summary", summary_table, doc.width))
    story.append(Spacer(1, 10))

    materials_rows = [[m.rm_name, m.quantity] for m in materials]
    if not materials_rows:
        materials_rows = [["No materials recorded", "-"]]
    materials_table = _build_data_table(
        ["Material", "Quantity"],
        materials_rows,
        doc.width,
        styles,
        target_height=125,
    )
    story.append(panel("Raw Material Consumption", materials_table, doc.width))
    story.append(Spacer(1, 10))

    half_width = (doc.width - 8) / 2

    chem_rows = [
        ["Protein", report.protein],
        ["Fat", report.fat],
        ["Fiber", report.fiber],
        ["Ash", report.ash],
        ["Calcium", report.calcium],
        ["Phosphorus", report.phosphorus],
        ["Salt", report.salt],
    ]
    chem_table = _build_data_table(
        ["Chemical Parameter", "Value"],
        chem_rows,
        half_width,
        styles,
        target_height=220,
    )

    phys_rows = [
        ["HM Retention", report.hm_retention],
        ["Mixer Moisture", report.mixer_moisture],
        ["Conditioner Moisture", report.conditioner_moisture],
        ["Moisture Addition", report.moisture_addition],
        ["Final Feed Moisture", report.final_feed_moisture],
        ["Water Activity", report.water_activity],
        ["Hardness", report.hardness],
        ["Pellet Diameter", report.pellet_diameter],
        ["Fines", report.fines],
    ]
    phys_table = _build_data_table(
        ["Physical Parameter", "Value"],
        phys_rows,
        half_width,
        styles,
        target_height=220,
    )

    bottom_tables = Table(
        [[panel("Chemical Analysis", chem_table, half_width), panel("Physical Parameters", phys_table, half_width)]],
        colWidths=[half_width, half_width],
    )
    bottom_tables.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(bottom_tables)
    story.append(PageBreak())

    graph_images = generate_plc_graph_images(
        plc_rows or [],
        width=int(doc.width),
        height=190,
    )
    if graph_images:
        graph_rows = [[graph[1]] for graph in graph_images]
        graph_stack = Table(graph_rows, colWidths=[doc.width])
        graph_stack.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("BOX", (0, 0), (-1, -1), 0.6, PDF_GRID),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, PDF_GRID),
                ]
            )
        )
        story.append(panel("Sensor Trends", graph_stack, doc.width))
    else:
        story.append(panel("Sensor Trends", Table([["No PLC data available for this batch"]], colWidths=[doc.width]), doc.width))

    decorator = _page_decorator("Production Batch Report", company_name, generated_at)
    doc.build(story, onFirstPage=decorator, onLaterPages=decorator)
    buffer.seek(0)
    return buffer.read()
