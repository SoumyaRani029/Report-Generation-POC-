# report_builder.py
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from pathlib import Path
from typing import Dict, Any, List, Tuple
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from PIL import Image
import tempfile
import os
from datetime import datetime
import json

# ====== PAGE GEOMETRY ======
PAGE_W, PAGE_H = A4
LEFT = 20 * mm
RIGHT = 20 * mm
TOP = 30 * mm
BOTTOM = 50 * mm
USABLE_W = PAGE_W - LEFT - RIGHT
USABLE_H = PAGE_H - TOP - BOTTOM

# ====== COLORS (match template) ======
DARK_GREEN = HexColor('#006747')     # CBRE banner green
LIGHT_GRAY = HexColor('#D9D9D9')     # Subsection header
CAPTION_GRAY = HexColor('#E0E0E0')   # Photo caption box
WHITE = colors.white
BLACK = colors.black
FOOTER_GRAY = colors.grey
 
# ====== TYPOGRAPHY ======
FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
 
# ====== HELPERS ======
def _draw_footer(c: canvas.Canvas, page_num: int, total_pages: int):
    c.saveState()
    c.setFont(FONT, 8)
    c.setFillColor(FOOTER_GRAY)
    c.drawString(LEFT, 15 * mm, f"Strictly Confidential Page {page_num} of {total_pages}")
    c.drawRightString(PAGE_W - RIGHT, 15 * mm, "CBRE - Valuation Advisory Services")
    c.restoreState()

def _draw_header_banner(c: canvas.Canvas, y: float, text: str, font_size=16) -> float:
    c.saveState()
    banner_h = 12 * mm
    c.setFillColor(DARK_GREEN)
    c.rect(LEFT, y - banner_h, USABLE_W, banner_h, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont(FONT_BOLD, font_size)
    c.drawCentredString(PAGE_W / 2, y - banner_h / 2 - 2, text)
    c.restoreState()
    return y - banner_h - 2 * mm

def _draw_subsection_header(c: canvas.Canvas, y: float, text: str, font_size=10) -> float:
    c.saveState()
    h = 6 * mm
    c.setFillColor(LIGHT_GRAY)
    c.rect(LEFT, y - h, USABLE_W, h, fill=1, stroke=0)
    c.setFillColor(BLACK)
    c.setFont(FONT_BOLD, font_size)
    c.drawString(LEFT + 2 * mm, y - h / 2 - 1.5, text)
    c.restoreState()
    return y - h - 2 * mm

def _paragraph(text: Any, font_size=9) -> Paragraph:
    styles = getSampleStyleSheet()
    style = ParagraphStyle(
    'CellStyle',
    parent=styles['Normal'],
        fontName=FONT,
    fontSize=font_size,
        leading=font_size + 4,
    spaceBefore=0,
        spaceAfter=0,
        wordWrap='LTR',
    )
    return Paragraph("" if text is None else str(text), style)

def _wrap_table_cells(data: List[List[Any]], font_size=9) -> List[List[Paragraph]]:
    return [[cell if isinstance(cell, Paragraph) else _paragraph(cell, font_size) for cell in row] for row in data]
 
def _table(data: List[List[Any]], col_widths: List[float], font_size=9, header_row=None, header_bg=None) -> Table:
    t = Table(_wrap_table_cells(data, font_size), colWidths=col_widths)
    style = [
        ('BACKGROUND', (0, 0), (-1, -1), WHITE),
        ('TEXTCOLOR', (0, 0), (-1, -1), BLACK),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('MINROWHEIGHT', (0, 0), (-1, -1), 12),
        ('FONTNAME', (0, 0), (-1, -1), FONT),
        ('FONTSIZE', (0, 0), (-1, -1), font_size),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, BLACK),
    ]
    if header_row is not None:
        style += [
            ('FONTNAME', (0, header_row), (-1, header_row), FONT_BOLD),
            ('BACKGROUND', (0, header_row), (-1, header_row), header_bg or LIGHT_GRAY),
        ]
    t.setStyle(TableStyle(style))
    return t
 
def _check_space_and_new_page(c, y, required_space, page_num, total_pages):
    buffer = 10 * mm
    if y < BOTTOM + required_space + buffer:
        _draw_footer(c, page_num, total_pages)
        c.showPage()
        page_num += 1
        y = PAGE_H - TOP
    return y, page_num
 
def _wrap_text(c, text, font_name, font_size, max_width, start_y, line_spacing=5 * mm, page_num=1, total_pages=1):
    if not text or str(text).strip() in {"N/A", "NA"}:
        return start_y, page_num
    words = str(text).split()
    line = ""
    y = start_y
    if y < BOTTOM + 30 * mm:
        _draw_footer(c, page_num, total_pages)
        c.showPage(); page_num += 1; y = PAGE_H - TOP
    for word in words:
        test = (line + word + " ") if line else (word + " ")
        if c.stringWidth(test, font_name, font_size) < max_width:
            line = test
        else:
            if line:
                if y < BOTTOM + 20 * mm:
                    _draw_footer(c, page_num, total_pages)
                    c.showPage(); page_num += 1; y = PAGE_H - TOP
                c.drawString(LEFT, y, line.strip()); y -= line_spacing
            line = word + " "
    if line:
        if y < BOTTOM + 20 * mm:
            _draw_footer(c, page_num, total_pages)
            c.showPage(); page_num += 1; y = PAGE_H - TOP
        c.drawString(LEFT, y, line.strip()); y -= line_spacing
    return y, page_num

def _draw_logo(c, y_top, table_h, logo_reserved_w=40 * mm):
    # Finds cbre_logo.png next to script; draws dark-green variant
    try:
        script_dir = Path(__file__).parent
    except NameError:
        script_dir = Path.cwd()
    logo_path = script_dir / "cbre_logo.png"
    if not logo_path.exists():
        c.saveState()
        c.setFillColor(DARK_GREEN)
        c.setFont(FONT_BOLD, 10)
        c.drawRightString(PAGE_W - RIGHT, y_top - table_h / 2, "CBRE")
        c.restoreState()
        return
    try:
        logo_x = LEFT + (USABLE_W - logo_reserved_w)
        logo_img = Image.open(logo_path).convert('RGBA')
        # recolor to #006747
        try:
            import numpy as np
            arr = np.array(logo_img)
            mask = arr[:, :, 3] > 0
            arr[mask, 0] = 0
            arr[mask, 1] = 103
            arr[mask, 2] = 71
            recol = Image.fromarray(arr, 'RGBA')
        except Exception:
            recol = logo_img
        white_bg = Image.new('RGB', recol.size, (255, 255, 255))
        white_bg.paste(recol, (0, 0), recol)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png"); tmp.close()
        white_bg.save(tmp.name, 'PNG')
        # fit height to table height + 10mm
        max_h = table_h + 4 * mm  # keep slightly taller than table
        aspect = white_bg.width / white_bg.height
        logo_h = min(32 * mm, max_h)  # cap height ~32 mm to control size
        logo_w = logo_h * aspect
        y = (y_top - table_h / 2) - logo_h / 2
        c.drawImage(tmp.name, logo_x, y, width=logo_w, height=logo_h, preserveAspectRatio=True, mask='auto')
        try: os.unlink(tmp.name)
        except: pass
    except Exception:
        c.saveState()
        c.setFillColor(DARK_GREEN)
        c.setFont(FONT_BOLD, 10)
        c.drawRightString(PAGE_W - RIGHT, y_top - table_h / 2, "CBRE")
        c.restoreState()
 
# ====== MAIN RENDERER (single pass) ======
def _render_once(c: canvas.Canvas, structured: Dict[str, Any], images: List[Path], location_map: Path, total_pages_for_footer: int) -> int:
    """Draws the entire report and returns the total pages used in this pass."""
    
    # Helper function to normalize empty values to "NA" - used throughout the report
    def normalize_field(value, default="NA"):
        """Normalize field value to 'NA' if empty, None, or null."""
        if value is None:
            return default
        val_str = str(value).strip()
        if val_str == "" or val_str.lower() in {"null", "none", "n/a", "na"}:
            return default
        return val_str
    
    page_num = 1
    val_date_display = structured.get("date_of_valuation", datetime.now().strftime("%B %d, %Y"))
 
    # === COVER / PAGE 1 ===
    y = PAGE_H - 10 * mm
    y = _draw_header_banner(c, y, "MARKET VALUATION REPORT", 16)
    y -= 2 * mm
 
    prop_ref = structured.get("property_reference_number", f"REF{datetime.now().strftime('%Y%m%d%H%M%S')}")
    header_data = [
        ["Property Reference Number:", prop_ref],
        ["Date of Valuation:", val_date_display],
    ]
    logo_reserved_w = 65 * mm
    tbl_w = USABLE_W - logo_reserved_w - 10 * mm
    header_col_widths = [tbl_w * 0.4, tbl_w * 0.6]
    header_table = _table(header_data, header_col_widths, font_size=9)
    _, h = header_table.wrap(tbl_w, PAGE_H)
    header_table.drawOn(c, LEFT, y - h)
    _draw_logo(c, y, h, logo_reserved_w=logo_reserved_w)
    y -= h + 5 * mm
 
    # === SECTION 1 ===
    y = _draw_header_banner(c, y, "SECTION 1 - PROPERTY DESCRIPTION", 12)
    
    # Photos note
    y -= 2 * mm
    y, page_num = _check_space_and_new_page(c, y, 30 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, " Photographs of Property")
    y -= 1 * mm
    y2 = _draw_simple_table_block(c, y, [["Photographs of Property:", "Attached on last page of the report."]],
                                  [USABLE_W * 0.4, USABLE_W * 0.6],
                                  page_num, total_pages_for_footer)
    page_num, y = y2[0], y2[1]
    
    # 1.1 Transacting Parties
    y -= 2 * mm
    y, page_num = _check_space_and_new_page(c, y, 60 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "1.1 Transacting Parties")
    y -= 1 * mm
    buyer = normalize_field(structured.get("buyer_name"), "NA")
    seller = normalize_field(structured.get("seller_name"), buyer if buyer != "NA" else "NA")
    contact_person = normalize_field(structured.get("contact_person"), buyer if buyer != "NA" else "NA")
    contact = normalize_field(structured.get("contact_number"), "NA")
    y = _draw_table_or_newpage(c, y, page_num, total_pages_for_footer,
        [["- Buyer (Home Loan Applicant):", buyer],
         ["- Seller (Registered Owner):", seller]],
        [USABLE_W * 0.4, USABLE_W * 0.6])
    
    # Contact row (3 cols)
    contact_data = [[f"- Contact Person (& Telephone No.):", contact_person, contact]]
    contact_tbl = _table(contact_data, [USABLE_W * 0.4, USABLE_W * 0.35, USABLE_W * 0.25], font_size=9)
    w, h = contact_tbl.wrap(USABLE_W, PAGE_H)
    if y - h < BOTTOM + 30 * mm:
        _draw_footer(c, page_num, total_pages_for_footer); c.showPage(); page_num += 1; y = PAGE_H - TOP
        w, h = contact_tbl.wrap(USABLE_W, PAGE_H)
    contact_tbl.drawOn(c, LEFT, y - h); y -= h
    
    # 1.2 Address
    y, page_num = _check_space_and_new_page(c, y, 120 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "1.2 Property Address"); y -= 1 * mm
    
    # Always add all address fields, using "NA" for empty values
    addr_rows = [
        ["Address 1", normalize_field(structured.get("address_1"), "NA")],
        ["Address 2", normalize_field(structured.get("address_2"), "NA")],
        ["Address 3", normalize_field(structured.get("address_3"), "NA")],
        ["Address 4", normalize_field(structured.get("address_4"), "NA")],
        ["Building Name", normalize_field(structured.get("building_name"), "NA")],
        ["Sub-Locality", normalize_field(structured.get("sub_locality"), "NA")],
        ["Locality", normalize_field(structured.get("locality"), "NA")],
        ["City", normalize_field(structured.get("city"), "NA")],
        ["Pin Code", normalize_field(structured.get("pin_code"), "NA")],
    ]
    y = _draw_table_or_newpage(c, y, page_num, total_pages_for_footer, addr_rows, [USABLE_W * 0.3, USABLE_W * 0.7])
    
    # GPS - Always show both fields, using "NA" if not available
    lat = normalize_field(structured.get("gps_latitude"), "NA")
    lon = normalize_field(structured.get("gps_longitude"), "NA")
    y -= 2 * mm
    y, page_num = _check_space_and_new_page(c, y, 40 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "GPS Coordinates"); y -= 1 * mm
    gps_rows = [
        ["Latitude", lat],
        ["Longitude", lon]
    ]
    y = _draw_table_or_newpage(c, y, page_num, total_pages_for_footer, gps_rows, [USABLE_W * 0.3, USABLE_W * 0.7])
    
    # 1.3 Surroundings
    y -= 2 * mm
    y, page_num = _check_space_and_new_page(c, y, 40 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "1.3 Location & Surroundings"); y -= 1 * mm
    surroundings_data = [
        ["- Use of Surrounding Land:", normalize_field(structured.get("surrounding_land_use"), "NA")],
        ["- Condition of Surroundings:", normalize_field(structured.get("surrounding_condition"), "NA")],
        ["- Negative Area:", normalize_field(structured.get("negative_area"), "NA")],
        ["- Outside City Limits:", normalize_field(structured.get("outside_city_limits"), "NA")]
    ]
    y = _draw_table_or_newpage(c, y, page_num, total_pages_for_footer, surroundings_data, [USABLE_W * 0.5, USABLE_W * 0.5])
 
    # Property Specific Info / 1.4 Area
    y -= 2 * mm
    y, page_num = _check_space_and_new_page(c, y, 80 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "PROPERTY SPECIFIC INFORMATION"); y -= 2 * mm
    y = _draw_subsection_header(c, y, "1.4 Property Area"); y -= 1 * mm
    
    land_area = normalize_field(structured.get("land_area_sft"), "NA")
    plot_demarcated = normalize_field(structured.get("plot_demarcated"), "NA")
    prop_ident = normalize_field(structured.get("ease_of_identification"), "NA")
    location_map_attached = "Yes" if (location_map and Path(location_map).exists()) else normalize_field(structured.get("location_map_attached"), "NA")
    nearby_landmark = normalize_field(structured.get("nearby_landmark"), "NA")
    prop_area_rows = [
        [f"- Land Area of Property (sft): If available {land_area}", f"- Plot Demarcated? {plot_demarcated}"],
        [f"- Ease of property identification: {prop_ident}", f"Location map / description attached: {location_map_attached}"],
        [f"- Nearby Landmark: {nearby_landmark}", "NA"],
    ]
    y = _draw_table_or_newpage(c, y, page_num, total_pages_for_footer, prop_area_rows, [USABLE_W * 0.6, USABLE_W * 0.4])
    
    # Built-up Area
    y -= 2 * mm
    y, page_num = _check_space_and_new_page(c, y, 140 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "BUILT-UP AREA"); y -= 1 * mm
    col_w = [USABLE_W * 0.28, USABLE_W * 0.18, USABLE_W * 0.36, USABLE_W * 0.18]
    bua_rows = [
        ["- Planned Area of Property (sft):", normalize_field(structured.get("planned_area_sft"), "NA"),
         normalize_field(structured.get("planned_area_source"), "NA"), normalize_field(structured.get("planned_area_type"), "NA")],
        ["- Permissible Area as per FAR (sft):", normalize_field(structured.get("permissible_area_far_sft"), "NA"), "NA",
         normalize_field(structured.get("permissible_area_type"), "NA")],
        ["- Actual Area of Property (sft):", normalize_field(structured.get("actual_area_sft"), "NA"),
         normalize_field(structured.get("actual_area_type"), "NA"), normalize_field(structured.get("actual_area_type"), "NA")],
        ["- Area adopted for Valuation (sft):", normalize_field(structured.get("area_adopted_for_valuation_sft"), "NA"),
         normalize_field(structured.get("area_adopted_type"), "NA"), normalize_field(structured.get("area_adopted_type"), "NA")],
        ["- Loading factor adopted", normalize_field(structured.get("loading_factor"), "NA"),
         normalize_field(structured.get("loading_factor_type"), "NA"), normalize_field(structured.get("loading_factor_type"), "NA")],
        ["- Deviation in Area?", normalize_field(structured.get("deviation_in_area"), "NA"),
         f"% deviation in area, specify: {normalize_field(structured.get('deviation_percent'), 'NA')}", "NA"],
    ]
    y = _draw_table_or_newpage(c, y, page_num, total_pages_for_footer, bua_rows, col_w)
    # Always show deviation acceptable field
    y = _draw_table_or_newpage(c, y, page_num, total_pages_for_footer,
               [["- Deviation Acceptable?", normalize_field(structured.get("deviation_acceptable"), "NA")]],
                               [USABLE_W * 0.4, USABLE_W * 0.6])
    # Always show area comments section, using "NA" if empty
    area_comments = normalize_field(structured.get("area_comments"), "NA")
    y -= 2 * mm; y, page_num = _check_space_and_new_page(c, y, 40 * mm, page_num, total_pages_for_footer)
    c.saveState(); c.setFont(FONT_BOLD, 9); c.drawString(LEFT, y, "Please enter Comments, if any"); y -= 4 * mm
    c.setFont(FONT, 9); y, page_num = _wrap_text(c, area_comments, FONT, 9, USABLE_W, y, 4 * mm, page_num, total_pages_for_footer)
    c.restoreState(); y -= 1 * mm
    
    # Floor height
    y -= 2 * mm
    y, page_num = _check_space_and_new_page(c, y, 70 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "FLOOR HEIGHT DEVIATION"); y -= 1 * mm
    floor_rows = [
        ["- Permitted Floor Height of Property (ft):", f"Maximum {normalize_field(structured.get('permitted_floor_height_max'), 'NA')} Minimum {normalize_field(structured.get('permitted_floor_height_min'), 'NA')}"],
        ["- Actual Floor Height of Property (ft):", normalize_field(structured.get("actual_floor_height_ft"), "NA")],
        ["- Deviation in Floor Height?", normalize_field(structured.get("deviation_in_floor_height"), "NA")],
        ["- Deviation Acceptable?", normalize_field(structured.get("floor_height_deviation_acceptable"), "NA")],
    ]
    y = _draw_table_or_newpage(c, y, page_num, total_pages_for_footer, floor_rows, [USABLE_W * 0.5, USABLE_W * 0.5])
    # Always show floor height comments section, using "NA" if empty
    floor_comments = normalize_field(structured.get("floor_height_comments"), "NA")
    c.saveState(); c.setFont(FONT, 9); c.drawString(LEFT, y, "Please enter Comments, if any"); y -= 5 * mm
    y, page_num = _wrap_text(c, floor_comments, FONT, 8, USABLE_W, y, 4 * mm, page_num, total_pages_for_footer)
    c.restoreState(); y -= 2 * mm
    
    # Setbacks
    y -= 3 * mm
    y, page_num = _check_space_and_new_page(c, y, 115 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "SET BACK DEVIATIONS"); y -= 1 * mm
    colw_sb = [USABLE_W * 0.3] + [USABLE_W * 0.175] * 4
    sb_data = [
        ["", "FRONT", "REAR", "LEFT SIDE", "RIGHT SIDE"],
        ["Permitted Set Backs (ft)", normalize_field(structured.get("permitted_setback_front_ft"), "NA"),
         normalize_field(structured.get("permitted_setback_rear_ft"), "NA"),
         normalize_field(structured.get("permitted_setback_left_ft"), "NA"),
         normalize_field(structured.get("permitted_setback_right_ft"), "NA")],
        ["Actual Set Backs (ft)", normalize_field(structured.get("actual_setback_front_ft"), "NA"),
         normalize_field(structured.get("actual_setback_rear_ft"), "NA"),
         normalize_field(structured.get("actual_setback_left_ft"), "NA"),
         normalize_field(structured.get("actual_setback_right_ft"), "NA")],
        ["Deviation in Set Backs?", normalize_field(structured.get("deviation_in_setback_front"), "NA"),
         normalize_field(structured.get("deviation_in_setback_rear"), "NA"),
         normalize_field(structured.get("deviation_in_setback_left"), "NA"),
         normalize_field(structured.get("deviation_in_setback_right"), "NA")],
        ["Specify Deviation %", normalize_field(structured.get("setback_deviation_percent_front"), "NA"),
         normalize_field(structured.get("setback_deviation_percent_rear"), "NA"),
         normalize_field(structured.get("setback_deviation_percent_left"), "NA"),
         normalize_field(structured.get("setback_deviation_percent_right"), "NA")],
    ]
    sb_table = _table(sb_data, colw_sb, font_size=9, header_row=0, header_bg=LIGHT_GRAY)
    w, h = sb_table.wrap(USABLE_W, PAGE_H)
    if y - h < BOTTOM + 30 * mm:
        _draw_footer(c, page_num, total_pages_for_footer); c.showPage(); page_num += 1; y = PAGE_H - TOP
        w, h = sb_table.wrap(USABLE_W, PAGE_H)
    sb_table.drawOn(c, LEFT, y - h); y -= h
    # Always show setback deviations acceptable field
    y = _draw_table_or_newpage(c, y, page_num, total_pages_for_footer,
               [["- Deviations Acceptable?", normalize_field(structured.get("setback_deviations_acceptable"), "NA")]],
                               [USABLE_W * 0.4, USABLE_W * 0.6])
    # Always show setback comments section, using "NA" if empty
    sb_comments = normalize_field(structured.get("setback_comments"), "NA")
    y -= 2 * mm; c.saveState(); c.setFont(FONT, 9); c.drawString(LEFT, y, "Please enter Comments, if any")
    y -= 5 * mm
    y, page_num = _wrap_text(c, sb_comments, FONT, 8, USABLE_W, y, 4 * mm, page_num, total_pages_for_footer)
    c.restoreState(); y -= 2 * mm
    
    # Projected construction
    y -= 2 * mm
    y, page_num = _check_space_and_new_page(c, y, 90 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "PROJECTED CONSTRUCTION"); y -= 1 * mm
    proj_rows = [
        ["- Projection(s) Sighted:", "Balcony", normalize_field(structured.get("projection_balcony"), "NA"),
         "Portico", normalize_field(structured.get("projection_portico"), "NA")],
        ["", "staircase", normalize_field(structured.get("projection_staircase"), "NA"),
         "Overhead tank", normalize_field(structured.get("projection_overhead_tank"), "NA")],
        ["", "Terrace", normalize_field(structured.get("projection_terrace"), "NA"),
         "Other(s)", normalize_field(structured.get("projection_others"), "NA")],
    ]
    proj_tbl = _table(proj_rows, [USABLE_W * 0.3, USABLE_W * 0.15, USABLE_W * 0.15, USABLE_W * 0.15, USABLE_W * 0.25])
    w, h = proj_tbl.wrap(USABLE_W, PAGE_H)
    if y - h < BOTTOM + 30 * mm:
        _draw_footer(c, page_num, total_pages_for_footer); c.showPage(); page_num += 1; y = PAGE_H - TOP
        w, h = proj_tbl.wrap(USABLE_W, PAGE_H)
    proj_tbl.drawOn(c, LEFT, y - h); y -= h
    y = _draw_table_or_newpage(c, y, page_num, total_pages_for_footer,
                               [[f"- Projection(s) a Public Nuisance?", normalize_field(structured.get("projection_public_nuisance"), "NA")],
                                [f"If Yes, specify reason thereof:", normalize_field(structured.get("projection_nuisance_reason"), "NA")]],
                               [USABLE_W * 0.5, USABLE_W * 0.5])
    
    # 1.5 Condition
    y -= 3 * mm
    y, page_num = _check_space_and_new_page(c, y, 70 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "1.5 Condition of Property"); y -= 1 * mm
    cond_rows = [
        ["- Year of Construction:", normalize_field(structured.get("year_of_construction"), "NA")],
        ["- Age of Property (years):", normalize_field(structured.get("age_years"), "NA")],
        [f"- Exterior Condition of Property: {normalize_field(structured.get('exterior_condition'), 'NA')}", f"If Poor, then reason thereon: {normalize_field(structured.get('exterior_condition_reason'), 'NA')}"],
        [f"- Interior Condition of Property: {normalize_field(structured.get('interior_condition'), 'NA')}", f"If Poor, then reason thereon: {normalize_field(structured.get('interior_condition_reason'), 'NA')}"],
        ["- Expected Future Physical Life of Property (years):", normalize_field(structured.get("expected_future_life_years"), "NA")],
    ]
    y = _draw_table_or_newpage(c, y, page_num, total_pages_for_footer, cond_rows, [USABLE_W * 0.5, USABLE_W * 0.5])

    # 1.6 Features & Amenities
    y -= 3 * mm
    y, page_num = _check_space_and_new_page(c, y, 110 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "1.6 Features & Amenities"); y -= 1 * mm
    feats = [
        [f"Bedroom(s) {normalize_field(structured.get('bedrooms'), 'NA')}", f"Bathroom(s) {normalize_field(structured.get('bathrooms'), 'NA')}"],
        [f"- Number of Rooms: Hall(s) {normalize_field(structured.get('halls'), 'NA')}", f"Kitchen(s) {normalize_field(structured.get('kitchens'), 'NA')}"],
        [f"Others {normalize_field(structured.get('other_rooms'), 'NA')}", "NA"],
        [f"- Number of Floors: In Building {normalize_field(structured.get('floors_in_building'), 'NA')}", f"In Property {normalize_field(structured.get('floors_in_property'), 'NA')}"],
        [f"- Number of Lift & Stairs: Lift(s) {normalize_field(structured.get('lifts'), 'NA')}", f"Stair(s) {normalize_field(structured.get('stairs'), 'NA')}"],
    ]
    y = _draw_table_or_newpage(c, y, page_num, total_pages_for_footer, feats, [USABLE_W * 0.5, USABLE_W * 0.5])
    
    # Amenities grid
    amenities_data = structured.get("amenities", "")
    parsed_amenities = []
    amenities_text = ""
    if isinstance(amenities_data, str):
        raw = amenities_data.strip()
        if raw and raw.upper() != "NA":
            try:
                candidate = json.loads(raw)
                if isinstance(candidate, list):
                    parsed_amenities = candidate
                else:
                    amenities_text = raw
            except (json.JSONDecodeError, TypeError):
                amenities_text = raw
    elif isinstance(amenities_data, list):
        parsed_amenities = amenities_data

    am_rows = [["Amenity", "One Time Charges (Rs)", "Recurring Charges per month (Rs)"]]
    for item in parsed_amenities:
        if isinstance(item, dict):
            am_rows.append([
                item.get("name", "N/A"),
                item.get("one_time_charges_rs", "NA"),
                item.get("recurring_charges_rs", "NA"),
            ])
        elif isinstance(item, str):
            am_rows.append([item, "NA", "NA"])
    
    if len(am_rows) > 1:
        table = _table(am_rows, [USABLE_W * 0.4, USABLE_W * 0.3, USABLE_W * 0.3], font_size=9, header_row=0, header_bg=LIGHT_GRAY)
        w, h = table.wrap(USABLE_W, PAGE_H)
        if y - h < BOTTOM + 30 * mm:
            _draw_footer(c, page_num, total_pages_for_footer)
            c.showPage()
            page_num += 1
            y = PAGE_H - TOP
            w, h = table.wrap(USABLE_W, PAGE_H)
        table.drawOn(c, LEFT, y - h)
        y -= h
    elif amenities_text:
        y -= 2 * mm
        c.saveState()
        c.setFont(FONT, 9)
        y, page_num = _wrap_text(c, amenities_text, FONT, 9, USABLE_W, y, 5 * mm, page_num, total_pages_for_footer)
        c.restoreState()
    
    # 1.7 Occupancy
    y -= 3 * mm
    y, page_num = _check_space_and_new_page(c, y, 60 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "1.7 Occupancy Status"); y -= 1 * mm
    y = _draw_table_or_newpage(c, y, page_num, total_pages_for_footer, [[structured.get("occupancy_status", "N/A")]], [USABLE_W])
    occ_cmt = structured.get("occupancy_comments", "")
    if occ_cmt:
        y -= 2 * mm; c.saveState(); c.setFont(FONT, 9)
        y, page_num = _wrap_text(c, occ_cmt, FONT, 9, USABLE_W, y, 5 * mm, page_num, total_pages_for_footer)
        c.restoreState()
 
    # 1.8 Stage
    y -= 5 * mm
    y, page_num = _check_space_and_new_page(c, y, 50 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "1.8 Stage of Construction"); y -= 1 * mm
    y = _draw_table_or_newpage(c, y, page_num, total_pages_for_footer,
                               [["- Percentage of Property Completion:", structured.get("percentage_completion", "100%")],
                                ["- Valuer's Comments on Construction:", structured.get("construction_comments", "NA")]],
                               [USABLE_W * 0.5, USABLE_W * 0.5])
    
    _draw_footer(c, page_num, total_pages_for_footer); c.showPage(); page_num += 1
    
    # === SECTION 2 ===
    y = PAGE_H - TOP
    y = _draw_header_banner(c, y, "MARKET SPECIFIC INFORMATION", 12)
    y -= 2 * mm
    y = _draw_subsection_header(c, y, "SECTION 2 - PROPERTY VALUATION")
    y -= 1 * mm
    y = _draw_subsection_header(c, y, "2.1 Market Comparables")
    y -= 1 * mm
    
    # Read comparables from new PDF-compatible format (_comparable_1, _comparable_2 suffixes)
    # Fallback to old list format for backward compatibility
    comp_col_w = [USABLE_W * 0.4, USABLE_W * 0.6]
    
    def get_comparable_field(idx: int, field: str, default: str = "N/A") -> str:
        """Get comparable field from new format (_comparable_1, _comparable_2) or old list format.
        Ensures all empty/None/null values are normalized to 'N/A'."""
        def normalize_value(value):
            """Normalize value to 'N/A' if empty, None, null, or contains only 'None'."""
            if value is None:
                return default
            val_str = str(value).strip()
            if val_str == "":
                return default
            # Check for variations of None/null/n/a (case-insensitive)
            val_lower = val_str.lower()
            if val_lower in {"null", "none", "n/a", "na"}:
                return default
            # Check for "None None" or similar patterns (remove spaces and hyphens first)
            val_no_spaces = val_lower.replace(" ", "").replace("-", "")
            if val_no_spaces in {"nonenone", "nullnull", "nana", "n/an/a"}:
                return default
            # Check if value is just whitespace or multiple "None" words
            words = [w.strip() for w in val_str.split() if w.strip()]
            if len(words) > 0 and all(word.lower() in {"none", "null", "na", "n/a"} for word in words):
                return default
            return val_str
        
        # Try new format first
        new_format_key = f"{field}_comparable_{idx}"
        if new_format_key in structured:
            val = structured[new_format_key]
            normalized = normalize_value(val)
            if normalized != default:
                if idx == 2 and field == "address_1":
                    print(f"[Report Builder] ✅ Found {new_format_key} = {normalized}")
                return normalized
            elif idx == 2 and field == "address_1":
                print(f"[Report Builder] ⚠️ {new_format_key} exists but value is empty/NA: {val}")
            # Return default even if key exists but value is empty/NA
            return default
        
        # Fallback to old list format
        comparables = structured.get("comparables", [])
        if isinstance(comparables, str):
            try: 
                comparables = json.loads(comparables)
            except: 
                comparables = []
        if isinstance(comparables, list) and len(comparables) >= idx:
            comp = comparables[idx - 1]
            if isinstance(comp, dict):
                val = comp.get(field, default)
                normalized = normalize_value(val)
                if normalized != default:
                    if idx == 2 and field == "address_1":
                        print(f"[Report Builder] ✅ Found {field} from comparables[{idx-1}] = {normalized}")
                    return normalized
                elif idx == 2 and field == "address_1":
                    print(f"[Report Builder] ⚠️ comparables[{idx-1}].{field} exists but value is empty/NA: {val}")
        
        if idx == 2 and field == "address_1":
            print(f"[Report Builder] ❌ Returning default '{default}' for Comparable #{idx}.{field}")
        return default
    
    # Debug: Check what comparable data is available
    pdf_fields_available = [k for k in structured.keys() if '_comparable_' in k]
    comparables_list_available = structured.get("comparables", [])
    print(f"[Report Builder] 🔍 Comparable data check:")
    print(f"   - PDF-compatible fields: {len(pdf_fields_available)}")
    print(f"   - Comparables list length: {len(comparables_list_available)}")
    if len(pdf_fields_available) > 0:
        print(f"   - Sample PDF fields: {pdf_fields_available[:3]}...")
    if len(comparables_list_available) > 0:
        print(f"   - Comparable #1 city: {comparables_list_available[0].get('city', 'N/A') if isinstance(comparables_list_available[0], dict) else 'N/A'}")
        if len(comparables_list_available) > 1:
            print(f"   - Comparable #2 city: {comparables_list_available[1].get('city', 'N/A') if isinstance(comparables_list_available[1], dict) else 'N/A'}")
    
    for idx in range(1, 3):
        c.saveState(); c.setFont(FONT_BOLD, 9); c.drawString(LEFT, y, f"COMPARABLE #{idx}"); c.restoreState()
        y -= 3 * mm
        
        # Get all fields for this comparable
        print(f"[Report Builder] 🔍 Getting fields for Comparable #{idx}")
        address_1 = get_comparable_field(idx, "address_1")
        if idx == 2:
            print(f"[Report Builder]   - address_1_comparable_2 = {address_1}")
        address_2 = get_comparable_field(idx, "address_2")
        address_3 = get_comparable_field(idx, "address_3")
        address_4 = get_comparable_field(idx, "address_4")
        building_name = get_comparable_field(idx, "building_name")
        sub_locality = get_comparable_field(idx, "sub_locality")
        locality = get_comparable_field(idx, "locality")
        city = get_comparable_field(idx, "city")
        pin_code = get_comparable_field(idx, "pin_code")
        date_of_transaction = get_comparable_field(idx, "date_of_transaction")
        approx_area_sft = get_comparable_field(idx, "approx_area_sft")
        land_area_sft = get_comparable_field(idx, "land_area_sft")
        approx_transaction_price_inr = get_comparable_field(idx, "approx_transaction_price_inr")
        approx_transaction_price_land_inr = get_comparable_field(idx, "approx_transaction_price_land_inr")
        transaction_price_per_sft_inr = get_comparable_field(idx, "transaction_price_per_sft_inr")
        transaction_price_per_sft_land_inr = get_comparable_field(idx, "transaction_price_per_sft_land_inr")
        source_of_information = get_comparable_field(idx, "source_of_information")
        
        # Format date and area display - ensure all values are "NA" if empty
        tdate = normalize_field(date_of_transaction, "NA") if date_of_transaction != "N/A" else "NA"
        tdisp = tdate
        a = normalize_field(approx_area_sft, "NA") if approx_area_sft != "N/A" else "NA"
        # Try to get area_type from old format for backward compatibility
        area_type = get_comparable_field(idx, "area_type", "Built Up Area")
        if area_type != "Built Up Area" and area_type != "N/A":
            adisp = f"{a} {area_type}" if a != "NA" else "NA"
        else:
            adisp = a if a != "N/A" else "NA"
        
        # Ensure all comparable fields are normalized to "NA" if empty - this prevents empty boxes
        comp_rows = [
            ["Address 1", normalize_field(address_1, "NA")], 
            ["Address 2", normalize_field(address_2, "NA")], 
            ["Address 3", normalize_field(address_3, "NA")], 
            ["Address 4", normalize_field(address_4, "NA")],
            ["Building Name", normalize_field(building_name, "NA")], 
            ["Sub-Locality", normalize_field(sub_locality, "NA")], 
            ["Locality", normalize_field(locality, "NA")],
            ["City", normalize_field(city, "NA")], 
            ["Pin Code", normalize_field(pin_code, "NA")],
            ["Date of Transaction:", normalize_field(tdisp, "NA")],
            ["Approx. Area of Property (sft):", normalize_field(adisp, "NA")],
            ["Land Area of Property (sft):", normalize_field(land_area_sft, "NA")],
            ["Approx. Transaction Price (INR):", normalize_field(approx_transaction_price_inr, "NA")],
            ["Approx. Transaction Price (INR): (Land)", normalize_field(approx_transaction_price_land_inr, "NA")],
            ["Transaction Price per sq. ft (INR):", normalize_field(transaction_price_per_sft_inr, "NA")],
            ["Transaction Price per sq. ft (INR): (Land)", normalize_field(transaction_price_per_sft_land_inr, "NA")],
            ["Source of Information:", normalize_field(source_of_information, "NA")],
        ]
        tbl = _table(comp_rows, comp_col_w, font_size=8)
        w, h = tbl.wrap(USABLE_W, PAGE_H)
        if y - h < BOTTOM + 30 * mm:
            _draw_footer(c, page_num, total_pages_for_footer); c.showPage(); page_num += 1; y = PAGE_H - TOP
            # section header persists on new page only for next blocks, not re-drawn here to match sample
        tbl.drawOn(c, LEFT, y - h); y -= h
 
    # 2.2 Prevailing values
    y -= 1 * mm
    y = _draw_subsection_header(c, y, "2.2 Prevailing Market Values"); y -= 1 * mm
    # Always show market value ranges, using "NA" if not available
    land_min = normalize_field(structured.get("market_value_range_land_psft_min"), "NA")
    land_max = normalize_field(structured.get("market_value_range_land_psft_max"), "NA")
    if land_min != "NA" and land_max != "NA":
        land_range = f"{land_min} to {land_max}"
    else:
        land_range = "NA"
    
    psft_min = normalize_field(structured.get("market_value_range_psft_min"), "NA")
    psft_max = normalize_field(structured.get("market_value_range_psft_max"), "NA")
    if psft_min != "NA" and psft_max != "NA":
        psft_range = f"{psft_min} to {psft_max}"
    else:
        psft_range = "NA"
    
    market_rows = [
        ["- Market value range for land (psft):", land_range],
        ["- Market value range (psft):", psft_range],
        ["- Information Obtained From:", normalize_field(structured.get("market_value_information_source"), "NA")]
    ]
    t = _table(market_rows, comp_col_w, font_size=9)
    w, h = t.wrap(USABLE_W, PAGE_H); t.drawOn(c, LEFT, y - h); y -= h
 
    # Valuation Analysis
    y -= 2 * mm
    y, page_num = _check_space_and_new_page(c, y, 70 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "VALUATION ANALYSIS"); y -= 1 * mm
    y = _draw_subsection_header(c, y, "2.3 Defining Market Value"); y -= 1 * mm
    mv_def = structured.get("market_value_definition",
        'Market Value is defined as "an opinion of the best price at which the sale of an interest in property would have been completed unconditionally for cash consideration on the date of the valuation, assuming (1) a willing seller; (2) that, prior to the date of valuation, there had been a reasonable period (having regard to the nature of the property and the state of the market) for the proper marketing of the interest and for the agreement of the sale price; (3) that, the state of the market, level of values and other circumstances were, on any earlier assumed date of exchange of contracts, the same as on the date of valuation; (4) that no account is taken of any additional bid by a prospective buyer with a special interest; (5) that both parties to the transaction had acted knowledgeably, prudently and without compulsion."')
    c.saveState(); c.setFont(FONT, 8)
    y, page_num = _wrap_text(c, mv_def, FONT, 8, USABLE_W, y, 4 * mm, page_num, total_pages_for_footer)
    c.restoreState()
    
    # 2.4 Market Value of Property
    y -= 5 * mm
    y, page_num = _check_space_and_new_page(c, y, 140 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "2.4 Market Value of Property"); y -= 1 * mm
    c.saveState(); c.setFont(FONT_BOLD, 9); c.drawString(LEFT, y, "BASE VALUE"); c.restoreState(); y -= 6 * mm
    val_date_short = "as on Date of Valuation"
    base_rows = [
        ["- Base Value of Property (for land) (Rs psft):", f"{normalize_field(structured.get('base_value_land_psft'), 'NA')} {val_date_short}"],
        ["- Base Value of Property (Rs psft):", f"{normalize_field(structured.get('base_value_built_psft'), 'NA')} {normalize_field(structured.get('base_value_type'), 'Built Up Area')} {val_date_short}"]
    ]
    y = _draw_table_or_newpage(c, y, page_num, total_pages_for_footer, base_rows, [USABLE_W * 0.5, USABLE_W * 0.5])
 
    # Charges
    y -= 3 * mm; c.setFont(FONT_BOLD, 9); c.drawString(LEFT, y, "APPLICABLE ADDITIONAL CHARGES"); y -= 6 * mm
    charges = [
        ["- Fixed Furniture & Fixtures:", normalize_field(structured.get("fixed_furniture_fixtures"), "NA"), f"Description: {normalize_field(structured.get('fixed_furniture_fixtures_description'), 'NA')}"],
        ["- Preferred Location Charge:", normalize_field(structured.get("preferred_location_charge"), "NA"), f"Description: {normalize_field(structured.get('preferred_location_charge_description'), 'NA')}"],
        ["- External Development Charge:", normalize_field(structured.get("external_development_charge"), "NA"), f"Description: {normalize_field(structured.get('external_development_charge_description'), 'NA')}"],
        ["- Car Park", normalize_field(structured.get("car_park_charge"), "NA"), f"Description: {normalize_field(structured.get('car_park_charge_description'), 'NA')}"],
        ["- Transfer Charges (Noida Only):", normalize_field(structured.get("transfer_charges"), "NA"), f"Description: {normalize_field(structured.get('transfer_charges_description'), 'NA')}"],
        ["- Sales Tax:", normalize_field(structured.get("sales_tax"), "NA"), f"Description: {normalize_field(structured.get('sales_tax_description'), 'NA')}"],
    ]
    t = _table(charges, [USABLE_W * 0.3, USABLE_W * 0.25, USABLE_W * 0.45], font_size=9)
    w, h = t.wrap(USABLE_W, PAGE_H)
    if y - h < BOTTOM + 30 * mm:
        _draw_footer(c, page_num, total_pages_for_footer); c.showPage(); page_num += 1; y = PAGE_H - TOP
        w, h = t.wrap(USABLE_W, PAGE_H)
    t.drawOn(c, LEFT, y - h); y -= h
 
    # Total
    y -= 3 * mm; c.saveState(); c.setFont(FONT_BOLD, 9); c.drawString(LEFT, y, "TOTAL VALUE"); c.restoreState(); y -= 6 * mm
    total_rows = [
        ["- Total Value of Property (INR):", f"{normalize_field(structured.get('total_value_inr'), 'NA')} {val_date_short}"],
        ["- Total Value of Amenities (INR):", f"{normalize_field(structured.get('total_value_amenities_inr'), 'NA')} {val_date_short}"],
        ["Documents provided by", normalize_field(structured.get("documents_provided_by"), "NA"), f"Description {normalize_field(structured.get('documents_description'), 'NA')}"],
    ]
    t = _table(total_rows, [USABLE_W * 0.4, USABLE_W * 0.35, USABLE_W * 0.25], font_size=9)
    w, h = t.wrap(USABLE_W, PAGE_H)
    if y - h < BOTTOM + 30 * mm:
        _draw_footer(c, page_num, total_pages_for_footer); c.showPage(); page_num += 1; y = PAGE_H - TOP
        w, h = t.wrap(USABLE_W, PAGE_H)
    t.drawOn(c, LEFT, y - h); y -= h
    
    # Valuer's Comments
    y -= 2 * mm
    y, page_num = _check_space_and_new_page(c, y, 90 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "VALUER'S COMMENTS"); y -= 1 * mm
    c.saveState(); c.setFont(FONT, 9)
    y, page_num = _wrap_text(c, normalize_field(structured.get("valuer_comments"), "NA"), FONT, 9, USABLE_W, y, 4 * mm, page_num, total_pages_for_footer)
    c.restoreState()

    # 2.5 Replacement
    y -= 5 * mm
    y, page_num = _check_space_and_new_page(c, y, 70 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "2.5 Replacement Value"); y -= 1 * mm
    repl_rows = [
        ["- Construction Cost per sft:", f"{normalize_field(structured.get('construction_cost_per_sft'), 'NA')} {normalize_field(structured.get('construction_cost_type'), 'Built Up Area')}"],
        ["- Replacement Value of Property (INR):", f"{normalize_field(structured.get('replacement_value_inr'), 'NA')} {val_date_short}"]
    ]
    y = _draw_table_or_newpage(c, y, page_num, total_pages_for_footer, repl_rows, [USABLE_W * 0.5, USABLE_W * 0.5])
    
    # 2.6 Declaration
    y -= 3 * mm
    y, page_num = _check_space_and_new_page(c, y, 70 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "2.6 Valuer's Declaration"); y -= 1 * mm
    decl = normalize_field(structured.get("valuer_declaration"),
        f"I confirm that the market value for the subject property as on {val_date_display} is INR {normalize_field(structured.get('total_value_inr'), 'NA')}/- and the value of amenities as on {val_date_display} is INR {normalize_field(structured.get('total_value_amenities_inr'), 'NA')}/- taking into consideration the market dynamics and the condition of the property, its location, and amenities available.")
    c.saveState(); c.setFont(FONT, 9)
    y, page_num = _wrap_text(c, decl, FONT, 9, USABLE_W, y, 5 * mm, page_num, total_pages_for_footer)
    c.restoreState()
    
    # Valuer code + signature
    y -= 10 * mm; c.saveState(); c.setFont(FONT, 9); c.drawString(LEFT, y, f"Valuer Code:  {normalize_field(structured.get('valuer_code'), 'NA')}"); c.restoreState()
    y -= 10 * mm; c.drawString(LEFT, y, "Valuer's Signature")
    
    # 2.7 Disclaimer
    y -= 15 * mm
    y, page_num = _check_space_and_new_page(c, y, 70 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "2.7 Disclaimer"); y -= 1 * mm
    c.saveState(); c.setFont(FONT, 9)
    y, page_num = _wrap_text(c, normalize_field(structured.get("disclaimer_text"), "Please note that the above is a valuation and not a structural survey. CBRE is not responsible to HSBC or the purchaser of the above property for any flaws and/or faults with the property not detected by the above Valuer."),
                             FONT, 9, USABLE_W, y, 5 * mm, page_num, total_pages_for_footer)
    c.restoreState()
    
    # Annexure
    y -= 5 * mm
    y, page_num = _check_space_and_new_page(c, y, 90 * mm, page_num, total_pages_for_footer)
    y = _draw_subsection_header(c, y, "ANNEXURE"); y -= 1 * mm
    docs = structured.get("documents_list", [])
    if isinstance(docs, str):
        try:
            # Try JSON parsing first (for double-quoted JSON format)
            docs = json.loads(docs)
        except (json.JSONDecodeError, ValueError):
            try:
                # If JSON fails, try ast.literal_eval (for Python single-quote format)
                import ast
                docs = ast.literal_eval(docs)
            except (ValueError, SyntaxError):
                # If both fail, try to extract as a list by replacing single quotes with double quotes
                try:
                    # Replace single quotes with double quotes for JSON parsing
                    docs_str = docs.replace("'", '"')
                    docs = json.loads(docs_str)
                except (json.JSONDecodeError, ValueError):
                    docs = []
    # Ensure docs is a list
    if not isinstance(docs, list):
            docs = []
    ann_rows = [["List of documents provided by HSBC", "Type of Area", "Remarks (If any)"]]
    if isinstance(docs, list):
        for d in docs:
            if isinstance(d, dict):
                name = d.get("document_name", "N/A")
                provided = d.get("provided", "NA")
                remarks = d.get("remarks", "NA")
                if name == "Type of Area" and provided not in ("NA", "Yes", "No"):
                    ann_rows.append([name, provided, remarks])
                else:
                    ann_rows.append([name, provided, remarks])
    if len(ann_rows) > 1:
        t = _table(ann_rows, [USABLE_W * 0.45, USABLE_W * 0.2, USABLE_W * 0.35], font_size=8, header_row=0, header_bg=LIGHT_GRAY)
        w, h = t.wrap(USABLE_W, PAGE_H)
        if y - h < BOTTOM + 30 * mm:
            _draw_footer(c, page_num, total_pages_for_footer)
            c.showPage()
            page_num += 1
            y = PAGE_H - TOP
            w, h = t.wrap(USABLE_W, PAGE_H)
        t.drawOn(c, LEFT, y - h)
        y -= h
    
    _draw_footer(c, page_num, total_pages_for_footer); c.showPage(); page_num += 1
    
    # Photos page
    y = PAGE_H - TOP
    y = _draw_header_banner(c, y, "PROPERTY PHOTOGRAPHS", 12)
    y -= 30 * mm
    
    if images:
        images_to_use = images[:5]
        captions = [
            "Photograph 1: Outside View of Property",
            "Photograph 2: Inside View of Property",
            "Photograph 3: View of Property Kitchen",
            "Photograph 4: Surrounding View from Property",
            "Photograph 5: Serial number board / signage in the vicinity",
        ]
        img_px = 140
        img_pt = 140.0
        img_mm = img_pt / 72.0 * 25.4
        spacing = 40 * mm
        cap_h = 14 * mm  # Increased from 12mm to 14mm for better visibility
        gap = 3 * mm
        row_gap = 30 * mm
        avail_w = USABLE_W - 10 * mm
        top_w = 2 * img_mm + spacing
        bot_w = 3 * img_mm + 2 * spacing
        if top_w > avail_w or bot_w > avail_w:
            sf_top = (avail_w - spacing) / (2 * img_mm) if top_w > avail_w else 1.0
            sf_bot = (avail_w - 2 * spacing) / (3 * img_mm) if bot_w > avail_w else 1.0
            sf = min(sf_top, sf_bot)
            img_mm *= sf
            img_pt *= sf
            top_w = 2 * img_mm + spacing
            bot_w = 3 * img_mm + 2 * spacing
        top_x0 = LEFT + 5 * mm + (avail_w - top_w) / 2
        bot_x0 = LEFT + 5 * mm + (avail_w - bot_w) / 2
        top_positions = [top_x0, top_x0 + img_mm + spacing]
        bot_positions = [bot_x0, bot_x0 + img_mm + spacing, bot_x0 + 2 * (img_mm + spacing)]

        y_top = y
        for i, img in enumerate(images_to_use[:2]):
            _draw_photo(c, img, top_positions[i], y_top, img_mm, img_pt, cap_h, gap, caption=captions[i])

        y_bottom = (y_top - img_mm - cap_h - gap) - row_gap
        for j, img in enumerate(images_to_use[2:5]):
            _draw_photo(c, img, bot_positions[j], y_bottom, img_mm, img_pt, cap_h, gap, caption=captions[j + 2])
 
    _draw_footer(c, page_num, total_pages_for_footer); c.showPage(); page_num += 1
 
    # Location map
    y = PAGE_H - TOP
    y = _draw_header_banner(c, y, "LOCATION MAP", 12)
    
    # CRITICAL: Validate location_map is actually a map (satellite view, Google Maps, etc.)
    # Only show if it's a valid map image, otherwise show "NA"
    is_valid_map = False
    if location_map and Path(location_map).exists():
        # Check filename for map-related keywords to validate it's likely a map
        location_map_name = Path(location_map).name.lower()
        map_keywords = ['google', 'maps', 'googlemaps', 'satellite', 'map', 'location', 'streetmap', 'aerial']
        
        # If filename contains map keywords, it's likely a valid map
        if any(keyword in location_map_name for keyword in map_keywords):
            is_valid_map = True
        else:
            # If no map keywords in filename, it might be a regular photo - don't show it
            is_valid_map = False
    
    if is_valid_map:
        try:
            c.drawImage(str(location_map), LEFT, 40 * mm, width=PAGE_W - LEFT - RIGHT, height=PAGE_H - 80 * mm, preserveAspectRatio=True, mask='auto')
        except Exception:
            c.saveState(); c.setStrokeColor(colors.grey)
            c.rect(LEFT, 40 * mm, PAGE_W - LEFT - RIGHT, PAGE_H - 80 * mm)
            c.setFont(FONT, 9); c.drawCentredString(PAGE_W / 2, PAGE_H / 2, "Location map not available"); c.restoreState()
    else:
        # Show "NA" if location map is not provided or not a valid map
        c.saveState()
        c.setStrokeColor(colors.grey)
        c.rect(LEFT, 40 * mm, PAGE_W - LEFT - RIGHT, PAGE_H - 80 * mm)
        c.setFont(FONT, 9)
        c.drawCentredString(PAGE_W / 2, PAGE_H / 2, "NA")
        c.restoreState()
 
    _draw_footer(c, page_num, total_pages_for_footer)
    # DO NOT showPage here; closing will finalize last page
    return page_num
 
def _draw_caption_box(c, x, y_bottom_of_image, w_mm, cap_h, text):
    c.saveState()
    # Use a slightly darker gray for better contrast
    c.setFillColor(HexColor('#D0D0D0'))  # Darker than CAPTION_GRAY for better visibility
    c.rect(x, y_bottom_of_image - cap_h, w_mm, cap_h, fill=1, stroke=0)
    # Add a border for better definition
    c.setStrokeColor(BLACK)
    c.setLineWidth(0.3)
    c.rect(x, y_bottom_of_image - cap_h, w_mm, cap_h, fill=0, stroke=1)
    c.setFillColor(BLACK)
    # Increased font size from 7 to 9 for better visibility
    c.setFont(FONT_BOLD, 9)
    pad = 2 * mm
    avail = w_mm - 2 * pad
    # simple one/two-line wrap centered
    words = text.split(); lines = []; line = ""
    for w in words:
        test = (line + w + " ") if line else (w + " ")
        if c.stringWidth(test, FONT_BOLD, 9) <= avail: line = test
        else: lines.append(line.strip()); line = w + " "
    if line: lines.append(line.strip())
    center_y = (y_bottom_of_image - cap_h / 2) - 1
    if len(lines) == 1:
        lw = c.stringWidth(lines[0], FONT_BOLD, 9)
        c.drawString(x + (w_mm - lw) / 2, center_y, lines[0])
    else:
        for i, ln in enumerate(lines[:2]):
            lw = c.stringWidth(ln, FONT_BOLD, 9)
            offset = 4 * mm if i == 0 else -4 * mm  # Slightly increased spacing
            c.drawString(x + (w_mm - lw) / 2, center_y + offset, ln)
    c.restoreState()

def _draw_photo(c, img_path, x, y_top, img_mm, img_pt, cap_h, gap, caption=None):
    # Border
    c.saveState(); c.setStrokeColor(BLACK); c.setLineWidth(0.5)
    c.rect(x, y_top - img_mm, img_mm, img_mm, fill=0, stroke=1); c.restoreState()
    # Image (fit 140×140pt square)
    try:
        im = Image.open(img_path)
        im.thumbnail((140, 140), Image.Resampling.LANCZOS)
        canvas_img = Image.new('RGB', (140, 140), 'white')
        px = (140 - im.width) // 2; py = (140 - im.height) // 2
        canvas_img.paste(im, (px, py))
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png"); tmp.close()
        canvas_img.save(tmp.name, 'PNG')
        c.drawImage(tmp.name, x, y_top - img_mm, width=img_pt, height=img_pt, preserveAspectRatio=False, mask='auto')
        try: os.unlink(tmp.name)
        except: pass
    except Exception:
        pass
    if caption:
        _draw_caption_box(c, x, y_top - img_mm - gap, img_mm, cap_h, caption)
 
def _draw_simple_table_block(c, y, data, colw, page_num, total_pages):
    result = _draw_table_or_newpage(c, y, page_num, total_pages, data, colw)
    return page_num, result
 
def _draw_table_or_newpage(c, y, page_num, total_pages, rows, widths):
    t = _table(rows, widths, font_size=9)
    w, h = t.wrap(USABLE_W, PAGE_H)
    if y - h < BOTTOM + 30 * mm:
        _draw_footer(c, page_num, total_pages)
        c.showPage(); page_num += 1; y = PAGE_H - TOP
        w, h = t.wrap(USABLE_W, PAGE_H)
    t.drawOn(c, LEFT, y - h); return y - h
 
# ====== PUBLIC API ======
def build_report_pdf(structured: Dict[str, Any], images: List[Path], out_path: Path, location_map: Path = None):
    """
    Two-pass rendering so the footer shows the correct 'Page X of Y'.
    """
    out_path = Path(out_path)
 
    # Pass 1 — render to temp to count pages
    tmp1 = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); tmp1.close()
    c1 = canvas.Canvas(tmp1.name, pagesize=A4)
    pages_used = _render_once(c1, structured, images, location_map, total_pages_for_footer=999)  # placeholder
    c1.save()
    
    # Pass 2 — render final with correct page count
    c2 = canvas.Canvas(str(out_path), pagesize=A4)
    _render_once(c2, structured, images, location_map, total_pages_for_footer=pages_used)
    c2.save()
 
    # cleanup temp
    try: os.unlink(tmp1.name)
    except: pass
 
    print(f"[PDF] Report saved to {out_path} with {pages_used} pages")
