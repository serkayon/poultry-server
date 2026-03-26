"""Generate professional invoices as PDF - Classic Invoice Layout."""
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas as canvas_module
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate


TEAL = colors.HexColor('#245658')
LIGHT_TEAL = colors.HexColor('#e8f4f4')
LIGHT_GRAY = colors.HexColor('#f5f5f5')
MID_GRAY = colors.HexColor('#cccccc')
DARK_GRAY = colors.HexColor('#333333')
WHITE = colors.white
BLACK = colors.black


def generate_invoice_pdf(dispatch_entry, products,
                         company_name="SERKAYON FEED MILL",
                         company_tagline="Industrail Inteligence",
                         company_address="[Trichy,Tamil Nadu, India]",
                         company_city="[620001]",
                         company_phone="Phone (+91) 9876543210",
                         company_fax="Fax (+91) 9876543210"):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch
    )

    story = []
    styles = getSampleStyleSheet()
    W = 6.7 * inch  # usable width

    def style(name, **kwargs):
        base = styles['Normal']
        return ParagraphStyle(name, parent=base, **kwargs)

    # ─────────────────────────────────────────
    # HEADER: Company Name  |  INVOICE
    # ─────────────────────────────────────────
    co_name_style = style('CoName', fontSize=16, fontName='Helvetica-Bold', textColor=DARK_GRAY)
    co_tag_style  = style('CoTag',  fontSize=9,  fontName='Helvetica',      textColor=colors.grey)
    inv_title_style = style('InvTitle', fontSize=22, fontName='Helvetica-Bold',
                             textColor=TEAL, alignment=TA_RIGHT)

    header_data = [[
        [Paragraph(company_name, co_name_style),
         Paragraph(company_tagline, co_tag_style)],
        Paragraph("INVOICE", inv_title_style)
    ]]
    header_table = Table(header_data, colWidths=[W * 0.6, W * 0.4])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)

    # Company address block under name
    addr_style = style('Addr', fontSize=8, textColor=colors.grey, leading=12)
    story.append(Paragraph(company_address, addr_style))
    story.append(Paragraph(company_city, addr_style))
    story.append(Paragraph(f"{company_phone}   Fax {company_fax}", addr_style))
    story.append(Spacer(1, 0.15 * inch))

    # ─────────────────────────────────────────
    # DIVIDER
    # ─────────────────────────────────────────
    story.append(HRFlowable(width=W, thickness=1.5, color=TEAL, spaceAfter=6))

    # ─────────────────────────────────────────
    # TO / SHIP TO  +  Invoice # / Date
    # ─────────────────────────────────────────
    inv_date = (dispatch_entry.date.strftime("%B %d, %Y")
                if hasattr(dispatch_entry.date, 'strftime')
                else str(dispatch_entry.date))
    inv_no = f"INV-{dispatch_entry.id:04d}"

    label_s  = style('Lbl',  fontSize=8, fontName='Helvetica-Bold', textColor=TEAL)
    value_s  = style('Val',  fontSize=9, fontName='Helvetica', leading=13)
    meta_lbl = style('MLbl', fontSize=8, fontName='Helvetica-Bold', textColor=TEAL, alignment=TA_RIGHT)
    meta_val = style('MVal', fontSize=9, fontName='Helvetica', alignment=TA_RIGHT)

    # Build "TO" block
    to_lines = [
        Paragraph("TO:", label_s),
        Paragraph(dispatch_entry.party_name, style('PName', fontSize=9, fontName='Helvetica-Bold')),
    ]
    if getattr(dispatch_entry, 'party_address', None):
        to_lines.append(Paragraph(dispatch_entry.party_address, value_s))
    if getattr(dispatch_entry, 'pincode', None):
        to_lines.append(Paragraph(f"Pincode: {dispatch_entry.pincode}", value_s))
    if getattr(dispatch_entry, 'party_phone', None):
        to_lines.append(Paragraph(f"Phone: {dispatch_entry.party_phone}", value_s))

    # Build "SHIP TO" block
    ship_lines = [
        Paragraph("SHIP TO:", label_s),
        Paragraph(dispatch_entry.party_name, style('SName', fontSize=9, fontName='Helvetica-Bold')),
    ]
    if getattr(dispatch_entry, 'party_address', None):
        ship_lines.append(Paragraph(dispatch_entry.party_address, value_s))
    if getattr(dispatch_entry, 'pincode', None):
        ship_lines.append(Paragraph(f"Pincode: {dispatch_entry.pincode}", value_s))
    if getattr(dispatch_entry, 'party_phone', None):
        ship_lines.append(Paragraph(f"Phone: {dispatch_entry.party_phone}", value_s))

    # Build invoice meta block
    meta_lines = [
        [Paragraph("INVOICE #", meta_lbl), Paragraph(inv_no, meta_val)],
        [Paragraph("DATE:", meta_lbl),    Paragraph(inv_date, meta_val)],
    ]
    meta_table = Table(meta_lines, colWidths=[1.1 * inch, 1.4 * inch])
    meta_table.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))

    addresses_data = [[to_lines, ship_lines, meta_table]]
    addresses_table = Table(addresses_data, colWidths=[W * 0.33, W * 0.37, W * 0.3])
    addresses_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(addresses_table)
    story.append(Spacer(1, 0.12 * inch))

    # ─────────────────────────────────────────
    # COMMENTS / SPECIAL INSTRUCTIONS
    # ─────────────────────────────────────────
    if getattr(dispatch_entry, 'notes', None):
        story.append(Paragraph(
            f"<b>COMMENTS OR SPECIAL INSTRUCTIONS:</b> {dispatch_entry.notes}",
            style('Notes', fontSize=8, textColor=DARK_GRAY)
        ))
        story.append(Spacer(1, 0.1 * inch))

    # ─────────────────────────────────────────
    # SALESPERSON / VEHICLE / DISPATCH INFO ROW
    # ─────────────────────────────────────────
    info_header = ['SALESPERSON', 'P.O. NUMBER', 'VEHICLE NO.', 'DISPATCH DATE', 'TERMS']
    info_vals   = [
        getattr(dispatch_entry, 'salesperson', ''),
        getattr(dispatch_entry, 'po_number', ''),
        getattr(dispatch_entry, 'vehicle_no', ''),
        inv_date,
        getattr(dispatch_entry, 'terms', 'As Agreed'),
    ]

    info_col_w = [W / 5] * 5
    info_table_data = [info_header, info_vals]
    info_table = Table(info_table_data, colWidths=info_col_w)
    info_table.setStyle(TableStyle([
        # Header row
        ('BACKGROUND',   (0, 0), (-1, 0), TEAL),
        ('TEXTCOLOR',    (0, 0), (-1, 0), WHITE),
        ('FONTNAME',     (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, 0), 8),
        ('ALIGN',        (0, 0), (-1, 0), 'CENTER'),
        ('TOPPADDING',   (0, 0), (-1, 0), 6),
        ('BOTTOMPADDING',(0, 0), (-1, 0), 6),
        # Data row
        ('FONTSIZE',     (0, 1), (-1, 1), 8),
        ('ALIGN',        (0, 1), (-1, 1), 'CENTER'),
        ('TOPPADDING',   (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING',(0, 1), (-1, -1), 5),
        ('BACKGROUND',   (0, 1), (-1, 1), LIGHT_GRAY),
        # Border
        ('GRID',         (0, 0), (-1, -1), 0.5, MID_GRAY),
        ('BOX',          (0, 0), (-1, -1), 1,   TEAL),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.12 * inch))

    # ─────────────────────────────────────────
    # LINE ITEMS TABLE
    # ─────────────────────────────────────────
    col_widths = [0.55 * inch, 2.5 * inch, 1.0 * inch, 1.3 * inch, 1.35 * inch]
    item_headers = ['QTY\n(BAGS)', 'DESCRIPTION', 'WEIGHT/BAG\n(KG)', 'UNIT PRICE\n(per KG)', 'TOTAL']

    items_data = [item_headers]
    total_weight = 0.0
    total_bags   = 0

    if products:
        for product in products:
            wt = product.total_weight
            price = getattr(dispatch_entry, 'price', None) or 0
            line_total = wt * price
            items_data.append([
                f"{product.num_bags:.0f}",
                product.product_type,
                f"{product.weight_per_bag:.2f}",
                f"Rs. {price:.2f}" if price else "",
                f"Rs. {line_total:.2f}" if price else f"{wt:.2f} kg",
            ])
            total_weight += wt
            total_bags   += int(product.num_bags)

    # Empty rows to fill space (like a real invoice template)
    empty_rows_needed = max(0, 6 - len(items_data) + 1)
    for _ in range(empty_rows_needed):
        items_data.append(['', '', '', '', ''])

    items_table = Table(items_data, colWidths=col_widths, repeatRows=1)

    row_count = len(items_data)
    items_table.setStyle(TableStyle([
        # Header
        ('BACKGROUND',    (0, 0), (-1, 0), TEAL),
        ('TEXTCOLOR',     (0, 0), (-1, 0), WHITE),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, 0), 8),
        ('ALIGN',         (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, 0), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        # Data rows
        ('FONTSIZE',      (0, 1), (-1, -1), 9),
        ('ALIGN',         (0, 1), (0, -1), 'CENTER'),
        ('ALIGN',         (1, 1), (1, -1), 'LEFT'),
        ('ALIGN',         (2, 1), (-1, -1), 'RIGHT'),
        ('VALIGN',        (0, 1), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 1), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 7),
        # Alternating rows
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        # Grid
        ('GRID',          (0, 0), (-1, -1), 0.5, MID_GRAY),
        ('BOX',           (0, 0), (-1, -1), 1,   TEAL),
        # Left padding for description
        ('LEFTPADDING',   (1, 0), (1, -1), 8),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 0.0 * inch))

    # ─────────────────────────────────────────
    # TOTALS SECTION (right-aligned box)
    # ─────────────────────────────────────────
    price = getattr(dispatch_entry, 'price', None) or 0
    subtotal = total_weight * price

    lbl_s = style('TLbl', fontSize=9, fontName='Helvetica',      alignment=TA_RIGHT)
    val_s = style('TVal', fontSize=9, fontName='Helvetica-Bold', alignment=TA_RIGHT)
    big_lbl = style('BLbl', fontSize=11, fontName='Helvetica-Bold', alignment=TA_RIGHT, textColor=TEAL)
    big_val = style('BVal', fontSize=11, fontName='Helvetica-Bold', alignment=TA_RIGHT, textColor=TEAL)

    summary_rows = [
        [Paragraph("SUBTOTAL", lbl_s),          Paragraph(f"Rs. {subtotal:.2f}", val_s)],
        [Paragraph("TOTAL WEIGHT (KG)", lbl_s),  Paragraph(f"{total_weight:.2f} kg", val_s)],
        [Paragraph("TOTAL BAGS", lbl_s),         Paragraph(str(total_bags), val_s)],
        [Paragraph("TOTAL DUE", big_lbl),        Paragraph(f"Rs. {subtotal:.2f}", big_val)],
    ]

    summary_col = [3.8 * inch, 2.9 * inch]
    summary_table = Table([[['', '']]] + [['']], colWidths=[sum(summary_col)])  # spacer trick

    # Proper summary table
    sum_t = Table(summary_rows, colWidths=summary_col)
    sum_t.setStyle(TableStyle([
        ('ALIGN',         (0, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        # Dividers
        ('LINEBELOW',     (0, 0), (-1, 0), 0.5, MID_GRAY),
        ('LINEBELOW',     (0, 1), (-1, 1), 0.5, MID_GRAY),
        ('LINEBELOW',     (0, 2), (-1, 2), 0.5, MID_GRAY),
        # Total due row
        ('BACKGROUND',    (0, -1), (-1, -1), LIGHT_TEAL),
        ('LINEABOVE',     (0, -1), (-1, -1), 1.5, TEAL),
        ('LINEBELOW',     (0, -1), (-1, -1), 1.5, TEAL),
        # Box
        ('BOX',           (0, 0), (-1, -1), 1, TEAL),
    ]))

    # Put summary on right side
    outer = Table([[None, sum_t]], colWidths=[W - sum(summary_col), sum(summary_col)])
    outer.setStyle(TableStyle([
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(outer)
    story.append(Spacer(1, 0.25 * inch))

    # ─────────────────────────────────────────
    # FOOTER: Terms & Signature
    # ─────────────────────────────────────────
    story.append(HRFlowable(width=W, thickness=0.5, color=MID_GRAY, spaceAfter=8))

    terms_lbl = style('TrLbl', fontSize=8, fontName='Helvetica-Bold', textColor=TEAL)
    terms_txt = style('TrTxt', fontSize=8, leading=12)
    sig_lbl   = style('SigLbl', fontSize=8, fontName='Helvetica-Bold', textColor=TEAL, alignment=TA_RIGHT)
    sig_line  = style('SigLn',  fontSize=9, alignment=TA_RIGHT)

    footer_data = [[
        [
            Paragraph("TERMS & CONDITIONS:", terms_lbl),
            Spacer(1, 4),
            Paragraph("1. Payment terms as agreed.", terms_txt),
            Paragraph("2. Goods once sold cannot be returned.", terms_txt),
            Paragraph("3. All disputes subject to local jurisdiction.", terms_txt),
        ],
        [
            Paragraph("Authorized Signature:", sig_lbl),
            Spacer(1, 28),
            Paragraph("_________________________________", sig_line),
            Paragraph(company_name, style('SigCo', fontSize=8, alignment=TA_RIGHT, textColor=colors.grey)),
        ]
    ]]

    footer_table = Table(footer_data, colWidths=[W * 0.55, W * 0.45])
    footer_table.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(footer_table)

    story.append(Spacer(1, 0.15 * inch))

    # Timestamp
    ts = style('TS', fontSize=7, textColor=colors.lightgrey, alignment=TA_CENTER)
    story.append(Paragraph(f"Generated on {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}", ts))

    doc.build(story)
    buffer.seek(0)
    return buffer


# ──────────────────────────────────────────────────────────
# DEMO: generate a sample invoice to verify layout
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    from dataclasses import dataclass, field
    from typing import List, Optional
    from datetime import date

    @dataclass
    class MockProduct:
        product_type: str
        num_bags: float
        weight_per_bag: float

        @property
        def total_weight(self):
            return self.num_bags * self.weight_per_bag

    @dataclass
    class MockDispatch:
        id: int = 1001
        date: date = date(2024, 10, 8)
        vehicle_no: str = "MH-12-AB-1234"
        party_name: str = "Fresh Farms Ltd."
        party_address: str = "45 Market Street, Industrial Area"
        pincode: str = "400001"
        party_phone: str = "+91 98765 43210"
        price: float = 85.50
        notes: str = "Handle with care. Deliver before 9 AM."
        salesperson: str = "Ravi Kumar"
        po_number: str = "PO-2024-0089"
        terms: str = "Net 30 Days"

    products = [
        MockProduct("Broiler Chicken Feed (Starter)", 20, 50.0),
        MockProduct("Layer Mash Premium",              15, 40.0),
        MockProduct("Grower Pellets Grade-A",          10, 25.0),
    ]

    dispatch = MockDispatch()
    buf = generate_invoice_pdf(
        dispatch, products,
        company_name="POULTRY MANAGEMENT SYSTEM",
        company_tagline="Quality Feed & Poultry Solutions",
        company_address="Plot 12, Agro Industrial Zone",
        company_city="Pune, MH 411001",
        company_phone="Phone (020) 555-0100",
        company_fax="(020) 555-0101",
    )

    out_path = "/mnt/user-data/outputs/sample_invoice.pdf"
    with open(out_path, "wb") as f:
        f.write(buf.read())
    print(f"Invoice saved to {out_path}")