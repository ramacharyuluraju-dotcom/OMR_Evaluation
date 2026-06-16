import sys
import os
import io
import itertools
import base64
import ssl
import pandas as pd
import cv2
import numpy as np
import fitz  # PyMuPDF

# Pyzbar decoding integration for live identity harvesting
try:
    import pyzbar.pyzbar as pyzbar
except ImportError:
    pyzbar = None

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
    QListWidget, QStackedWidget, QLabel, QLineEdit, QPushButton, \
    QComboBox, QSlider, QProgressBar, QTableWidget, QTableWidgetItem, \
    QFileDialog, QFrame, QHeaderView
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap, QFont

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

DATASET_DIR = "omr_training_data/needs_review"
os.makedirs(DATASET_DIR, exist_ok=True)

# ==============================================================================
# PART 1: OPTIMIZED PDF GENERATOR LOGIC
# ==============================================================================
DROPOUT_GREY = colors.Color(0.6, 0.6, 0.6)
OMR_PAGE_W, OMR_PAGE_H = A4
OMR_MARGIN = 10 * mm
OMR_CONTENT_W = OMR_PAGE_W - (2 * OMR_MARGIN)

def draw_official_header(c, width, y_top, left_logo, right_logo, inst_name, inst_address, inst_affiliation, inst_accreditation, is_caed=False, compact=False):
    c.saveState()
    if compact:
        logo_size = 18 * mm; font_main = 14; font_sub1 = 8; font_sub2 = 7.5; font_sub3 = 7; spacing = 4 * mm
    else:
        logo_size = 22 * mm; font_main = 16; font_sub1 = 9.5; font_sub2 = 9; font_sub3 = 8.5; spacing = 5 * mm

    margin_x = 8 * mm if is_caed else 10 * mm
    if left_logo:
        try:
            img = ImageReader(left_logo)
            c.drawImage(img, margin_x, y_top - logo_size + (spacing/2), width=logo_size, height=logo_size, mask='auto', preserveAspectRatio=True)
        except: pass
    if right_logo:
        try:
            img = ImageReader(right_logo)
            right_x = width - margin_x - logo_size
            c.drawImage(img, right_x, y_top - logo_size + (spacing/2), width=logo_size, height=logo_size, mask='auto', preserveAspectRatio=True)
        except: pass

    c.setFillColor(colors.black)
    center_x = width / 2
    
    c.setFont("Helvetica-Bold", font_main)
    c.drawCentredString(center_x, y_top, inst_name)
    c.setFont("Helvetica", font_sub1)
    c.drawCentredString(center_x, y_top - spacing, inst_address)
    c.setFont("Helvetica", font_sub2)
    c.drawCentredString(center_x, y_top - (2*spacing), inst_affiliation)
    c.setFont("Helvetica-Bold", font_sub3)
    c.drawCentredString(center_x, y_top - (3*spacing), inst_accreditation)
    
    c.restoreState()
    return y_top - (3*spacing) - 2*mm

def draw_omr_watermark(c, watermark_stream):
    if watermark_stream:
        try:
            c.saveState()
            c.setFillAlpha(0.08)
            img = ImageReader(watermark_stream)
            img_w, img_h = 130 * mm, 130 * mm
            c.drawImage(img, (OMR_PAGE_W - img_w)/2, (OMR_PAGE_H - img_h)/2, width=img_w, height=img_h, mask='auto', preserveAspectRatio=True)
            c.restoreState()
        except: pass

def draw_omr_titles_and_serial(c, y_start, exam_type):
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(OMR_PAGE_W / 2, y_start - 3*mm, exam_type.upper())
    c.setFont("Helvetica-Bold", 14)
    omr_title_y = y_start - 9*mm
    c.drawCentredString(OMR_PAGE_W / 2, omr_title_y, "OMR ANSWER SHEET")
    
    c.setFont("Helvetica-Bold", 10)
    c.drawString(OMR_MARGIN, omr_title_y, "Serial No:  ________________")
    return y_start - 11*mm

def draw_omr_details_with_qr(c, y_start, student_name, usn, course_code):
    total_h = 22 * mm
    y_bottom = y_start - total_h
    c.saveState(); c.setStrokeColor(DROPOUT_GREY); c.setLineWidth(1)
    c.rect(OMR_MARGIN, y_bottom, OMR_CONTENT_W, total_h)
    mid_x = OMR_PAGE_W - OMR_MARGIN - 45*mm 
    c.line(mid_x, y_bottom, mid_x, y_start)
    c.restoreState() 
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 11)
    text_x = OMR_MARGIN + 5*mm
    c.drawString(text_x, y_start - 7*mm, f"Student Name:  {student_name}")
    c.drawString(text_x, y_start - 13.5*mm, f"USN:           {usn}")
    c.drawString(text_x, y_start - 20*mm, f"Course Code:   {course_code}")
    
    qr_data = f"{usn}|{student_name}|{course_code}"
    qr_code = qr.QrCodeWidget(qr_data)
    bounds = qr_code.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    qr_size = 20 * mm
    d = Drawing(qr_size, qr_size, transform=[qr_size/width, 0, 0, qr_size/height, 0, 0])
    d.add(qr_code)
    renderPDF.draw(d, c, mid_x + 12.5*mm, y_bottom + 1*mm)
    return y_bottom - 2*mm 

def draw_omr_instructions_compact(c, y_start):
    box_h = 12 * mm 
    y_bottom = y_start - box_h
    c.saveState(); c.setStrokeColor(DROPOUT_GREY); c.rect(OMR_MARGIN, y_bottom, OMR_CONTENT_W, box_h); c.restoreState()
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 8)
    
    c.drawString(OMR_MARGIN + 3*mm, y_start - 3.5*mm, "INSTRUCTIONS TO STUDENTS:")
    c.setFont("Helvetica-Bold", 7.2)
    
    c.setFillColor(colors.black)
    c.drawString(OMR_MARGIN + 46*mm, y_start - 3.5*mm, "1. Before marking on OMR sheet verify your USN, Name and Course Code.")
    
    c.setFont("Helvetica", 7)
    c.drawString(OMR_MARGIN + 3*mm, y_start - 7.0*mm, "2. Use Black Ball Point Pen ONLY.")
    c.drawString(OMR_MARGIN + 3*mm, y_start - 10.0*mm, "3. No extra marking on OMR sheet.")
    c.drawString(OMR_MARGIN + 52*mm, y_start - 7.0*mm, "4. Darken the circle completely.")
    c.drawString(OMR_MARGIN + 52*mm, y_start - 10.0*mm, "5. Multiple markings are invalid.")
    
    mid_right_x = OMR_PAGE_W - OMR_MARGIN - 50*mm
    labels_y = y_start - 4.5*mm
    c.setFont("Helvetica-Bold", 7); c.drawString(mid_right_x, labels_y, "CORRECT:")
    c.saveState(); c.setFillColor(DROPOUT_GREY); c.circle(mid_right_x + 20*mm, labels_y + 1.5*mm, 3*mm, fill=1, stroke=0); c.restoreState()
    c.drawString(mid_right_x, labels_y - 6*mm, "WRONG:")
    gap = 8*mm; start_ex = mid_right_x + 15*mm; ex_y = labels_y - 6*mm + 1.5*mm 
    c.saveState(); c.setStrokeColor(DROPOUT_GREY)
    c.circle(start_ex, ex_y, 3*mm); c.line(start_ex-2*mm, ex_y-2*mm, start_ex+2*mm, ex_y+2*mm); c.line(start_ex-2*mm, ex_y+2*mm, start_ex+2*mm, ex_y-2*mm)
    c.circle(start_ex+gap, ex_y, 3*mm); c.line(start_ex+gap-2*mm, ex_y, start_ex+gap-0.5*mm, ex_y-2*mm); c.line(start_ex+gap-0.5*mm, ex_y-2*mm, start_ex+gap+2*mm, ex_y+2*mm)
    c.circle(start_ex+2*gap, ex_y, 3*mm); p = c.beginPath(); p.moveTo(start_ex+2*gap, ex_y); p.arc(start_ex+2*gap-3*mm, ex_y-3*mm, start_ex+2*gap+3*mm, ex_y+3*mm, 90, 180); p.close(); c.setFillColor(DROPOUT_GREY); c.drawPath(p, fill=1, stroke=0)
    c.restoreState()
    return y_bottom - 2*mm

def draw_signatures_block(c, y_start):
    sig_h = 10 * mm; sig_bottom = y_start - sig_h; col_w = OMR_CONTENT_W / 3
    c.saveState(); c.setStrokeColor(DROPOUT_GREY); c.rect(OMR_MARGIN, sig_bottom, OMR_CONTENT_W, sig_h)
    c.line(OMR_MARGIN + col_w, sig_bottom, OMR_MARGIN + col_w, y_start); c.line(OMR_MARGIN + 2*col_w, sig_bottom, OMR_MARGIN + 2*col_w, y_start); c.restoreState()
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(OMR_MARGIN + col_w/2, y_start - 3.5*mm, "Student's Signature")
    c.drawCentredString(OMR_MARGIN + 1.5*col_w, y_start - 3.5*mm, "Date")
    c.drawCentredString(OMR_MARGIN + 2.5*col_w, y_start - 3.5*mm, "Invigilator's Signature")
    return sig_bottom - 2*mm

def draw_isolated_version_block(c, y_start):
    box_h = 8 * mm
    y_bottom = y_start - box_h
    c.saveState(); c.setStrokeColor(DROPOUT_GREY)
    c.rect(OMR_MARGIN, y_bottom, OMR_CONTENT_W, box_h)
    c.restoreState()
    
    anchor_s = 5 * mm
    c.setFillColor(colors.black)
    c.rect(OMR_MARGIN + 1.5*mm, y_bottom + (box_h - anchor_s)/2, anchor_s, anchor_s, fill=1, stroke=0)
    
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 10)
    c.drawString(OMR_MARGIN + 10*mm, y_bottom + 2.8*mm, "Question Paper Version Code:")
    bubble_y = y_bottom + 4*mm 
    start_x = OMR_MARGIN + 75*mm 
    spacing = 11 * mm 
    c.setStrokeColor(DROPOUT_GREY)
    for i, opt in enumerate(['A', 'B', 'C', 'D']):
        bx = start_x + (i*spacing)
        c.circle(bx, bubble_y, 3.2*mm)
        c.setFillColor(DROPOUT_GREY); c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(bx, bubble_y - 1*mm, opt)
    return y_bottom - 4*mm

def draw_4_corner_question_block(c, x_start, y_start, block_w, num_qs):
    if num_qs <= 50:
        cols, rows, row_h, b_spacing, b_rad = 3, 17, 7.5*mm, 7.5*mm, 3.0*mm
    else:
        cols, rows, row_h, b_spacing, b_rad = 4, 25, 6.2*mm, 6.8*mm, 2.9*mm
        
    group_gap = 2.5 * mm 
    num_gaps = (rows - 1) // 5
    block_h = (rows * row_h) + (num_gaps * group_gap) + 8*mm
    y_bottom = y_start - block_h
    
    anchor_s = 5 * mm
    c.setFillColor(colors.black)
    c.rect(x_start, y_start - anchor_s, anchor_s, anchor_s, fill=1, stroke=0) 
    c.rect(x_start + block_w - anchor_s, y_start - anchor_s, anchor_s, anchor_s, fill=1, stroke=0) 
    c.rect(x_start, y_bottom, anchor_s, anchor_s, fill=1, stroke=0) 
    c.rect(x_start + block_w - anchor_s, y_bottom, anchor_s, anchor_s, fill=1, stroke=0) 
    
    col_w = block_w / cols
    q_start_x = x_start + anchor_s + 2*mm
    q_start_y = y_start - anchor_s - 2*mm
    
    c.saveState()
    c.setStrokeColor(DROPOUT_GREY)
    c.setDash(2, 2)
    for col in range(1, cols):
        div_x = q_start_x + (col * col_w) - 5*mm
        c.line(div_x, y_start - anchor_s, div_x, y_bottom + anchor_s)
    c.restoreState()

    q_current = 1
    for col in range(cols):
        curr_y = q_start_y
        for row in range(rows):
            if q_current > num_qs: break
            if row > 0 and row % 5 == 0: curr_y -= group_gap
            cx = q_start_x + (col * col_w)
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 9)
            c.drawRightString(cx + 4.5*mm, curr_y, f"{q_current}.")
            bubble_start = cx + 9.5*mm
            c.setStrokeColor(DROPOUT_GREY)
            for i, opt in enumerate(['A', 'B', 'C', 'D']):
                bx = bubble_start + (i*b_spacing)
                by = curr_y + 1.2*mm
                c.circle(bx, by, b_rad) 
                c.setFillColor(DROPOUT_GREY)
                c.setFont("Helvetica", 6.5)
                c.drawCentredString(bx, by - 1*mm, opt)
            curr_y -= row_h
            q_current += 1
    return y_bottom

def generate_batch_omr_pdf(inst_name, inst_address, inst_affiliation, inst_accreditation, left_logo, right_logo, watermark, students_data, course_code, exam_type, num_qs):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    for _, student in students_data.iterrows():
        usn = str(student.get('USN', student.iloc[0]))
        name = str(student.get('Name', student.iloc[1]))
        draw_omr_watermark(c, watermark)
        y_start = OMR_PAGE_H - 12*mm 
        curr_y = draw_official_header(c, OMR_PAGE_W, y_start, left_logo, right_logo, inst_name, inst_address, inst_affiliation, inst_accreditation)
        curr_y = draw_omr_titles_and_serial(c, curr_y, exam_type) 
        curr_y = draw_omr_details_with_qr(c, curr_y, name, usn, course_code) 
        curr_y = draw_omr_instructions_compact(c, curr_y)
        curr_y = draw_signatures_block(c, curr_y)
        curr_y = draw_isolated_version_block(c, curr_y)
        if num_qs <= 50:
            block_w = 150 * mm 
            draw_4_corner_question_block(c, (OMR_PAGE_W - block_w) / 2, curr_y, block_w, 50)
        else:
            block_w = 190 * mm 
            draw_4_corner_question_block(c, (OMR_PAGE_W - block_w) / 2, curr_y, block_w, 100)
        c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

def generate_caed_pdf(inst_name, inst_address, inst_affiliation, inst_accreditation, left_logo, right_logo):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4); margin = 5 * mm; content_w = width - 2*margin
    y_header_start = height - 10*mm
    header_bottom_y = draw_official_header(c, width, y_header_start, left_logo, right_logo, inst_name, inst_address, inst_affiliation, inst_accreditation, is_caed=True)
    title_line_y = header_bottom_y - 6*mm
    c.setFont("Helvetica-Bold", 12); c.drawCentredString(width/2, title_line_y, "PRINTOUT SHEET FOR ALL COMPUTER AIDED DRAWING SUBJECTS")
    serial_box_w = 35 * mm; serial_box_h = 7 * mm; serial_x = width - margin - serial_box_w; serial_y = title_line_y - 2.5*mm 
    c.rect(serial_x, serial_y, serial_box_w, serial_box_h); c.setFont("Helvetica-Bold", 10); c.drawString(serial_x - 18*mm, serial_y + 2*mm, "Serial No:")
    drawing_top = serial_y - 5*mm
    footer_height = 15 * mm; footer_bottom_y = margin; footer_top_y = footer_bottom_y + footer_height
    c.setLineWidth(1); c.rect(margin, footer_bottom_y, content_w, footer_height)
    col1 = content_w * 0.15; col2 = content_w * 0.25; col3 = content_w * 0.25; col4 = content_w * 0.35; x = margin
    c.line(x+col1, footer_bottom_y, x+col1, footer_top_y); c.setFont("Helvetica-Bold", 10); c.drawString(x+5*mm, footer_bottom_y + 5*mm, "Question No:")
    x += col1; c.line(x+col2, footer_bottom_y, x+col2, footer_top_y); c.drawString(x+5*mm, footer_bottom_y + 5*mm, "USN:")
    x += col2; c.line(x+col3, footer_bottom_y, x+col3, footer_top_y); c.drawString(x+5*mm, footer_bottom_y + 5*mm, "Student's Signature")
    x += col2; ex_w = col4 / 2; c.line(x+ex_w, footer_bottom_y, x+ex_w, footer_top_y); c.drawString(x+5*mm, footer_bottom_y + 5*mm, "Examiner 1"); c.drawString(x+ex_w+5*mm, footer_bottom_y + 5*mm, "Examiner 2")
    drawing_bottom = footer_top_y + 5*mm; drawing_height = drawing_top - drawing_bottom
    c.setLineWidth(1.5); c.rect(margin, drawing_bottom, content_w, drawing_height)
    c.showPage(); c.save(); buffer.seek(0)
    return buffer

def draw_diary_form(c, start_y, width, inst_name, inst_address, inst_affiliation, inst_accreditation, left_logo, right_logo):
    margin = 10 * mm; content_w = width - 2*margin
    y = draw_official_header(c, width, start_y, left_logo, right_logo, inst_name, inst_address, inst_affiliation, inst_accreditation, compact=True)
    c.setFont("Helvetica-Bold", 12); c.drawCentredString(width/2, y - 5*mm, "RELIEVING SUPERINTENDENT'S DIARY")
    c.setFont("Helvetica-Bold", 10); c.drawCentredString(width/2, y - 10*mm, "B.E./B.Arch/M.Tech/M.B.A/M.C.A/M.Arch Semester Examination ...........................")
    y -= 20 * mm; c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, "Centre: ........................................................................"); c.drawString(width - margin - 60*mm, y, "Date: ........................")
    y -= 8 * mm; c.drawString(margin, y, "Name of Relieving Superintendent: ........................................................................"); c.drawString(width - margin - 60*mm, y, "Time: ........... to ...........")
    y -= 8 * mm; c.drawString(margin, y, "Centre Code: ........................")
    y -= 5 * mm; table_top = y; row_h = 7 * mm; header_h = 12 * mm; num_rows = 7; table_h = header_h + (num_rows * row_h)
    col1 = content_w * 0.08; col2 = content_w * 0.12; col3 = content_w * 0.30; col4 = content_w * 0.25; col5 = content_w * 0.25
    c.rect(margin, table_top - table_h, content_w, table_h); x = margin
    c.line(x+col1, table_top, x+col1, table_top - table_h); x += col1; c.line(x+col2, table_top, x+col2, table_top - table_h); x += col2; c.line(x+col3, table_top, x+col3, table_top - table_h); x += col3; c.line(x+col4, table_top, x+col4, table_top - table_h)
    c.line(margin, table_top - header_h, width - margin, table_top - header_h)
    time_x = margin + col1 + col2 + col3; sig_x = time_x + col4
    c.line(time_x, table_top - (header_h/2), width - margin, table_top - (header_h/2))
    c.line(time_x + col4/2, table_top - (header_h/2), time_x + col4/2, table_top - table_h); c.line(sig_x + col5/2, table_top - (header_h/2), sig_x + col5/2, table_top - table_h)
    c.setFont("Helvetica-Bold", 8); c.drawCentredString(margin + col1/2, table_top - 7*mm, "S.No."); c.drawCentredString(margin + col1 + col2/2, table_top - 7*mm, "Block No."); c.drawCentredString(margin + col1 + col2 + col3/2, table_top - 7*mm, "Name of Room Supdt.")
    c.drawCentredString(time_x + col4/2, table_top - 4*mm, "Time of Relief"); c.drawCentredString(time_x + col4/4, table_top - 10*mm, "From"); c.drawCentredString(time_x + 3*col4/4, table_top - 10*mm, "To")
    c.drawCentredString(sig_x + col5/2, table_top - 4*mm, "Signature"); c.drawCentredString(sig_x + col5/4, table_top - 10*mm, "Relieving"); c.drawCentredString(sig_x + 3*col5/4, table_top - 10*mm, "Room Supdt")
    y_row = table_top - header_h
    for i in range(num_rows):
        c.line(margin, y_row - row_h, width - margin, y_row - row_h); c.drawString(margin + 2*mm, y_row - 5*mm, str(i+1)); y_row -= row_h
    foot_y = table_top - table_h - 15*mm; c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, foot_y, "Signature of Relieving Superintendent"); c.drawRightString(width - margin, foot_y, "Signature of Chief Superintendent")

def generate_diary_pdf(inst_name, inst_address, inst_affiliation, inst_accreditation, left_logo, right_logo):
    buffer = io.BytesIO(); c = canvas.Canvas(buffer, pagesize=A4); width, height = A4
    draw_diary_form(c, height - 5*mm, width, inst_name, inst_address, inst_affiliation, inst_accreditation, left_logo, right_logo)
    c.setDash(3, 3); c.line(10*mm, height/2, width - 10*mm, height/2); c.setDash(1, 0)
    draw_diary_form(c, (height/2) - 5*mm, width, inst_name, inst_address, inst_affiliation, inst_accreditation, left_logo, right_logo)
    c.showPage(); c.save(); buffer.seek(0)
    return buffer

# ==============================================================================
# PART 2: ADVANCED COMPUTER VISION ENGINE WITH WARPED VERSION MAPPING
# ==============================================================================
CONFIG_50Q = {
    'warped_w': 1450, 'warped_h': 1380, 'cols': 3, 'rows': 17, 'col_w': 1500 / 3.0,    
    'start_x': 140, 'start_y': 33, 'b_spacing': 75, 'row_h': 75, 'group_gap': 25, 'b_radius': 30, 'total_q': 50
}
CONFIG_100Q = {
    'warped_w': 1850, 'warped_h': 1680, 'cols': 4, 'rows': 25, 'col_w': 1900 / 4.0,    
    'start_x': 140, 'start_y': 33, 'b_spacing': 68, 'row_h': 62, 'group_gap': 25, 'b_radius': 29, 'total_q': 100
}

def find_anchors_and_warp(image, config):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mean_brightness = cv2.mean(gray)[0]
    if mean_brightness < 60: return "TOO_DARK", None, gray, None, None, None
        
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    cnts, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    
    candidates = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if w == 0 or h == 0: continue
        aspect_ratio = w / float(h)
        extent = cv2.contourArea(c) / area if area > 0 else 0
        if 50 < area < 5000 and 0.60 <= aspect_ratio <= 1.45 and extent > 0.85:
            candidates.append({"pt": (x + w//2, y + h//2), "area": area, "x": x + w//2, "y": y + h//2, "w": w})
            
    if len(candidates) < 5: return None, thresh, gray, None, None, None
        
    candidates.sort(key=lambda c: c["area"], reverse=True)
    top_candidates = candidates[:20] 
    
    min_error = float('inf')
    best_corners = None
    
    for combo in itertools.combinations(top_candidates, 4):
        cx = np.mean([c['x'] for c in combo])
        cy = np.mean([c['y'] for c in combo])
        try:
            tl = [c for c in combo if c['x'] < cx and c['y'] < cy][0]
            tr = [c for c in combo if c['x'] > cx and c['y'] < cy][0]
            bl = [c for c in combo if c['x'] < cx and c['y'] > cy][0]
            br = [c for c in combo if c['x'] > cx and c['y'] > cy][0]
        except IndexError: continue
            
        w = (tr['x'] - tl['x'] + br['x'] - bl['x']) / 2.0
        h = (bl['y'] - tl['y'] + br['y'] - tr['y']) / 2.0
        if w < 100 or h < 100: continue
            
        error = (abs(tl['x'] - bl['x']) + abs(tr['x'] - br['x'])) / w + (abs(tl['y'] - tr['y']) + abs(bl['y'] - br['y'])) / h
        if error < min_error:
            min_error = error
            best_corners = [tl, tr, br, bl] 
            
    if not best_corners: return None, thresh, gray, None, None, None
        
    grid_top_y = min(best_corners[0]['y'], best_corners[1]['y'])
    grid_center_x = (best_corners[0]['x'] + best_corners[1]['x']) / 2.0
    valid_versions = [c for c in top_candidates if c not in best_corners and c['y'] < grid_top_y and c['x'] < grid_center_x]
    version_anchor = max(valid_versions, key=lambda c: c['area']) if valid_versions else None

    src_pts = np.array([c['pt'] for c in best_corners], dtype="float32")
    dst_pts = np.array([[0, 0], [config['warped_w'], 0], [config['warped_w'], config['warped_h']], [0, config['warped_h']]], dtype="float32")
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped_color = cv2.warpPerspective(image, M, (config['warped_w'], config['warped_h']))
    warped_gray = cv2.warpPerspective(gray, M, (config['warped_w'], config['warped_h']))
    warped_thresh = cv2.adaptiveThreshold(warped_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 15)
    return best_corners, thresh, gray, version_anchor, warped_thresh, warped_color, M

def evaluate_image(image, multi_master_key, fill_percentage, config):
    flagged_log = []
    
    harvested_usn, harvested_name, harvested_course = "Unknown USN", "Unknown Student", "Unknown Course"
    if pyzbar is not None:
        try:
            detected_qrs = pyzbar.decode(image)
            if not detected_qrs:
                detected_qrs = pyzbar.decode(cv2.resize(image, (0,0), fx=0.5, fy=0.5))
            if detected_qrs:
                qr_string = detected_qrs[0].data.decode('utf-8')
                tokens = qr_string.split('|')
                if len(tokens) >= 3:
                    harvested_usn, harvested_name, harvested_course = tokens[0], tokens[1], tokens[2]
        except Exception:
            pass

    res = find_anchors_and_warp(image, config)
    if res[0] == "TOO_DARK":
        return {
            "USN": "ERR_DARK", "Name": "Unreadable", "Course": "Unreadable", "Version": "N/A", 
            "Status": "Scan rejected: Dark Matrix", "Score": 0, "Confidence": "0%", 
            "Flagged Questions": "Invalid Scan", "Needs Moderation": "YES"
        }, image.copy(), None
        
    if res[0] is None:
        return {
            "USN": "ERR_ALIGN", "Name": "Unreadable", "Course": "Unreadable", "Version": "N/A", 
            "Status": "Failed: Structural Anchors Lost", "Score": 0, "Confidence": "0%", 
            "Flagged Questions": "Anchors Lost", "Needs Moderation": "YES"
        }, image.copy(), None
        
    corners, thresh, gray, version_anchor, warped_thresh, warped_color, M = res
    debug_original = image.copy()
    for c in corners:
        cv2.rectangle(debug_original, (c['x']-15, c['y']-15), (c['x']+15, c['y']+15), (0, 0, 255), 3)
        
    flags_count, needs_moderation, detected_version = 0, "NO", "A"
    
    # SYSTEM CORRECTION: Robust Warped Version Code Mapping Engine
    if version_anchor is not None:
        v_pt = np.array([[[version_anchor['x'], version_anchor['y']]]], dtype="float32")
        warped_v_pt = cv2.perspectiveTransform(v_pt, M)[0][0]
        wx, wy = warped_v_pt[0], warped_v_pt[1]
        
        mm_to_px = config['warped_w'] / (150.0 if config['total_q'] == 50 else 190.0)
        b_rad_px = int(3.2 * mm_to_px)
        
        # FIX: Calculate an Inner Radius so the mask ignores the printed black bubble outline
        inner_rad_px = int(b_rad_px * 0.85)
        inner_area_px = 3.1415 * (inner_rad_px ** 2)

        # FIX: Output a debug image locally to verify exact mapping coordinates visually
        try:
            v_roi_x1 = max(0, int(wx + 60 * mm_to_px))
            v_roi_x2 = min(warped_color.shape[1], int(wx + 120 * mm_to_px))
            v_roi_y1 = max(0, int(wy - 15 * mm_to_px))
            v_roi_y2 = min(warped_color.shape[0], int(wy + 15 * mm_to_px))
            version_roi = warped_color[v_roi_y1:v_roi_y2, v_roi_x1:v_roi_x2]
            cv2.imwrite(f"DEBUG_Version_ROI_{harvested_usn}.jpg", version_roi)
        except Exception:
            pass
        
        v_fills = []
        for i, opt in enumerate(['A', 'B', 'C', 'D']):
            bx = int(wx + (71.0 + i * 11.0) * mm_to_px)
            by = int(wy)
            
            cv2.circle(warped_color, (bx, by), b_rad_px, (255, 0, 0), 2)
            
            mask = np.zeros(warped_thresh.shape, dtype="uint8")
            # Draw smaller radius into the mask to avoid border interference
            cv2.circle(mask, (bx, by), inner_rad_px, 255, -1) 
            
            fill_ratio = cv2.countNonZero(cv2.bitwise_and(warped_thresh, warped_thresh, mask=mask)) / inner_area_px
            v_fills.append((fill_ratio, opt, bx, by))
            
        # FIX: Lower the threshold slightly just for Version block to be more forgiving
        version_threshold = fill_percentage * 0.75 
        valid_versions = [v for v in v_fills if v[0] > version_threshold]
        
        if len(valid_versions) == 1:
            detected_version = valid_versions[0][1]
            cv2.circle(warped_color, (valid_versions[0][2], valid_versions[0][3]), b_rad_px + 3, (0, 200, 0), 3)
        elif len(valid_versions) > 1:
            detected_version = "Multiple"
            flags_count += 1; needs_moderation = "YES"
            flagged_log.append("Version Multi-Marked")
            for v in valid_versions:
                cv2.circle(warped_color, (v[2], v[3]), b_rad_px + 3, (0, 165, 255), 3)
        else:
            detected_version = "Blank"
            flags_count += 1; needs_moderation = "YES"
            flagged_log.append("Version Blank")
    else:
        detected_version = "Missing"
        flags_count += 1; needs_moderation = "YES"
        flagged_log.append("Version Anchor Lost")
            
    actual_score, final_status = 0, "Evaluated Successfully"
    active_key = multi_master_key.get(detected_version, {}) if detected_version in ['A', 'B', 'C', 'D'] else multi_master_key.get('A', {})
    if detected_version not in ['A', 'B', 'C', 'D']:
        final_status = f"Warning: Version '{detected_version}' Invalid."
        
    q_current = 1
    bubble_area = 3.1415 * (config['b_radius'] ** 2)
    for col in range(config['cols']):
        curr_y = config['start_y']
        for row in range(config['rows']):
            if q_current > config['total_q']: break
            if row > 0 and row % 5 == 0: curr_y += config['group_gap']
            b_start_x = config['start_x'] + (col * config['col_w'])
            fills = []
            for i in range(4):
                bx, by = int(b_start_x + (i * config['b_spacing'])), int(curr_y)
                cv2.circle(warped_color, (bx, by), config['b_radius'], (255, 180, 180), 1)
                mask = np.zeros(warped_thresh.shape, dtype="uint8")
                cv2.circle(mask, (bx, by), config['b_radius'], 255, -1)
                ratio = cv2.countNonZero(cv2.bitwise_and(warped_thresh, warped_thresh, mask=mask)) / bubble_area
                fills.append((ratio, i))
                
            valid_marks = [f for f in fills if f[0] > fill_percentage]
            ans_str = "Blank"
            if len(valid_marks) == 1:
                ans_str = ['A', 'B', 'C', 'D'][valid_marks[0][1]]
                best_idx = valid_marks[0][1]
                bx, by = int(b_start_x + (best_idx * config['b_spacing'])), int(curr_y)
                correct_answers = active_key.get(q_current, [])
                if not isinstance(correct_answers, list): correct_answers = [correct_answers]
                if ans_str in correct_answers:
                    actual_score += 1
                    cv2.circle(warped_color, (bx, by), config['b_radius']+3, (0, 200, 0), 3)
                else:
                    cv2.circle(warped_color, (bx, by), config['b_radius']+3, (0, 0, 255), 3)
            elif len(valid_marks) > 1:
                ans_str = "Multiple"
                flags_count += 1; needs_moderation = "YES"
                flagged_log.append(f"Q{q_current}")
                for fm in valid_marks:
                    bx, by = int(b_start_x + (fm[1] * config['b_spacing'])), int(curr_y)
                    cv2.circle(warped_color, (bx, by), config['b_radius']+3, (0, 165, 255), 3)
            q_current += 1
            curr_y += config['row_h']
            
    return {
        "USN": harvested_usn, "Name": harvested_name, "Course": harvested_course,
        "Version": detected_version, "Status": final_status, "Score": actual_score, 
        "Confidence": f"{max(5, 100 - (flags_count * 2))}%",
        "Flagged Questions": ", ".join(flagged_log) if flagged_log else "None", 
        "Needs Moderation": needs_moderation
    }, debug_original, warped_color

# ==============================================================================
# PART 3: QT WORKER THREADS
# ==============================================================================
class GenerationWorker(QThread):
    status_signal = Signal(str, str)
    
    def __init__(self, state, save_path, fmt, inst_name, inst_address, inst_affiliation, inst_accreditation, crs, exam, qs):
        super().__init__()
        self.state = state; self.save_path = save_path; self.fmt = fmt
        self.inst_name = inst_name; self.inst_address = inst_address
        self.inst_affiliation = inst_affiliation; self.inst_accreditation = inst_accreditation
        self.crs = crs; self.exam = exam; self.qs = qs
        
    def run(self):
        try:
            if self.fmt == "CAED Printout Sheet":
                pdf_buf = generate_caed_pdf(self.inst_name, self.inst_address, self.inst_affiliation, self.inst_accreditation, self.state["left_logo"], self.state["right_logo"])
            elif self.fmt == "Relieving Superintendent Diary":
                pdf_buf = generate_diary_pdf(self.inst_name, self.inst_address, self.inst_affiliation, self.inst_accreditation, self.state["left_logo"], self.state["right_logo"])
            else:
                if self.state["students_df"] is None:
                    self.status_signal.emit("❌ Error: Please upload Student Details CSV first.", "red")
                    return
                pdf_buf = generate_batch_omr_pdf(
                    self.inst_name, self.inst_address, self.inst_affiliation, self.inst_accreditation, 
                    self.state["left_logo"], self.state["right_logo"], 
                    self.state["watermark"], self.state["students_df"], self.crs, self.exam, self.qs
                )
                
            with open(self.save_path, "wb") as f:
                f.write(pdf_buf.getbuffer())
            self.status_signal.emit(f"✅ Saved successfully to: {os.path.basename(self.save_path)}", "green")
        except Exception as e:
            self.status_signal.emit(f"❌ Generation Error: {str(e)}", "red")

class EvaluationWorker(QThread):
    progress_signal = Signal(int, str)
    row_signal = Signal(dict)
    finished_signal = Signal()
    
    def __init__(self, paths, key_dict, fill_val, cfg):
        super().__init__()
        self.paths = paths; self.key_dict = key_dict; self.fill_val = fill_val; self.cfg = cfg
        
    def run(self):
        total = len(self.paths)
        for idx, path in enumerate(self.paths):
            filename = os.path.basename(path)
            self.progress_signal.emit(idx + 1, f"Processing {idx+1}/{total}: {filename}")
            
            try:
                if path.lower().endswith('.pdf'):
                    doc = fitz.open(path)
                    for p_num in range(len(doc)):
                        pix = doc.load_page(p_num).get_pixmap(dpi=200)
                        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                        if pix.n == 4: img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
                        elif pix.n == 3: img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                        elif pix.n == 1: img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                        
                        res, _, _ = evaluate_image(img, self.key_dict, self.fill_val / 100.0, self.cfg)
                        res["File Name"] = f"{filename} (Pg {p_num+1})"
                        self.row_signal.emit(res)
                    doc.close()
                else:
                    img = cv2.imread(path)
                    if img is not None:
                        res, _, _ = evaluate_image(img, self.key_dict, self.fill_val / 100.0, self.cfg)
                        res["File Name"] = filename
                        self.row_signal.emit(res)
                    else:
                        self.row_signal.emit({"USN": "Error", "Score": 0, "Confidence": "0%", "Flagged Questions": "Unreadable File", "File Name": filename})
            except Exception as e:
                self.row_signal.emit({"USN": "Error", "Score": 0, "Confidence": "0%", "Flagged Questions": f"Crash: {str(e)}", "File Name": filename})
        self.finished_signal.emit()

# ==============================================================================
# PART 4: DESKTOP WORKSPACE PANELS
# ==============================================================================
class GeneratorPanel(QWidget):
    def __init__(self, global_state):
        super().__init__()
        self.state = global_state
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30); layout.setSpacing(14)
        
        title = QLabel("<h2>🖨️ Document Template Generator</h2>")
        layout.addWidget(title)
        
        self.format_dropdown = QComboBox()
        self.format_dropdown.addItems(["OMR Answer Sheet", "CAED Printout Sheet", "Relieving Superintendent Diary"])
        layout.addWidget(QLabel("Select Sheet Format:"))
        layout.addWidget(self.format_dropdown)
        
        self.inst_name = QLineEdit("AMC ENGINEERING COLLEGE")
        layout.addWidget(QLabel("Name of Institute:"))
        layout.addWidget(self.inst_name)
        
        self.inst_address = QLineEdit("AMC Campus, Bannerghatta Road, Bengaluru, Karnataka - 560083")
        layout.addWidget(QLabel("Address of Institute:"))
        layout.addWidget(self.inst_address)
        
        self.inst_affiliation = QLineEdit("Autonomous Institution Affiliated to VTU, Belagavi")
        layout.addWidget(QLabel("Affiliation / Sub-Address Data:"))
        layout.addWidget(self.inst_affiliation)

        self.inst_accreditation = QLineEdit("Approved by AICTE, New Delhi | NAAC A+ Accredited")
        layout.addWidget(QLabel("Accreditation Data:"))
        layout.addWidget(self.inst_accreditation)
        
        self.course_code = QLineEdit("22CS61")
        self.lbl_cc = QLabel("Course / Subject Code:")
        layout.addWidget(self.lbl_cc); layout.addWidget(self.course_code)
        
        self.exam_type = QComboBox()
        self.exam_type.addItems(["Semester End Examination", "Continuous Internal Evaluation", "Lab Assessment Examination"])
        self.lbl_et = QLabel("Examination Description Identifier:")
        layout.addWidget(self.lbl_et); layout.addWidget(self.exam_type)
        
        self.num_qs = QComboBox()
        self.num_qs.addItems(["50 Questions", "100 Questions"])
        self.lbl_nq = QLabel("OMR Total Questions Architecture:")
        layout.addWidget(self.lbl_nq); layout.addWidget(self.num_qs)
        
        btn_layout = QHBoxLayout()
        self.btn_left = QPushButton("Upload Left Logo"); self.lbl_left = QLabel("Default: None")
        self.btn_right = QPushButton("Upload Right Logo"); self.lbl_right = QLabel("Default: None")
        btn_layout.addWidget(self.btn_left); btn_layout.addWidget(self.lbl_left)
        btn_layout.addWidget(self.btn_right); btn_layout.addWidget(self.lbl_right)
        layout.addLayout(btn_layout)
        
        btn_layout_2 = QHBoxLayout()
        self.btn_watermark = QPushButton("Upload Watermark"); self.lbl_watermark = QLabel("Default: None")
        self.btn_csv = QPushButton("Upload Student Dataset (CSV)"); self.lbl_csv = QLabel("Required for OMR sheets")
        btn_layout_2.addWidget(self.btn_watermark); btn_layout_2.addWidget(self.lbl_watermark)
        btn_layout_2.addWidget(self.btn_csv); btn_layout_2.addWidget(self.lbl_csv)
        layout.addLayout(btn_layout_2)
        
        self.gen_btn = QPushButton("Generate PDF Document")
        self.gen_btn.setObjectName("PrimaryAction")
        layout.addWidget(self.gen_btn)
        
        self.status_lbl = QLabel("")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_lbl)
        layout.addStretch()
        
        self.format_dropdown.currentTextChanged.connect(self.toggle_format_fields)
        self.btn_left.clicked.connect(lambda: self.pick_file("left_logo", self.lbl_left, "Images (*.png *.jpg *.jpeg)"))
        self.btn_right.clicked.connect(lambda: self.pick_file("right_logo", self.lbl_right, "Images (*.png *.jpg *.jpeg)"))
        self.btn_watermark.clicked.connect(lambda: self.pick_file("watermark", self.lbl_watermark, "Images (*.png *.jpg *.jpeg)"))
        self.btn_csv.clicked.connect(self.pick_csv)
        self.gen_btn.clicked.connect(self.trigger_generation)

    def toggle_format_fields(self, val):
        is_omr = (val == "OMR Answer Sheet")
        self.course_code.setVisible(is_omr); self.lbl_cc.setVisible(is_omr)
        self.exam_type.setVisible(is_omr); self.lbl_et.setVisible(is_omr)
        self.num_qs.setVisible(is_omr); self.lbl_nq.setVisible(is_omr)
        self.btn_watermark.setVisible(is_omr); self.lbl_watermark.setVisible(is_omr)
        self.btn_csv.setVisible(is_omr); self.lbl_csv.setVisible(is_omr)

    def pick_file(self, key, label, filters):
        path, _ = QFileDialog.getOpenFileName(self, "Open Resource File", "", filters)
        if path:
            self.state[key] = path
            label.setText(f"Selected: {os.path.basename(path)}")

    def pick_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Student CSV File", "", "CSV Data (*.csv)")
        if path:
            try:
                self.state["students_df"] = pd.read_csv(path)
                self.lbl_csv.setText(f"Loaded: {os.path.basename(path)}")
            except Exception as e:
                self.lbl_csv.setText(f"Error reading CSV: {str(e)}")

    def trigger_generation(self):
        fmt = self.format_dropdown.currentText()
        default_name = f"Batch_{self.course_code.text() or 'Document'}.pdf" if fmt == "OMR Answer Sheet" else f"{fmt.replace(' ', '_')}.pdf"
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Document Stream", default_name, "PDF Applications (*.pdf)")
        if not save_path: return
        
        self.gen_btn.setEnabled(False)
        self.gen_btn.setText("⏳ Building Document Stream Architecture...")
        
        inst = self.inst_name.text(); add = self.inst_address.text()
        aff = self.inst_affiliation.text(); acc = self.inst_accreditation.text()
        crs = self.course_code.text(); exam = self.exam_type.currentText()
        qs = 50 if "50" in self.num_qs.currentText() else 100
        
        self.worker = GenerationWorker(self.state, save_path, fmt, inst, add, aff, acc, crs, exam, qs)
        self.worker.status_signal.connect(self.handle_finish)
        self.worker.start()

    def handle_finish(self, text, color):
        self.status_lbl.setText(text)
        self.status_lbl.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.gen_btn.setEnabled(True)
        self.gen_btn.setText("Generate PDF Document")


class EvaluatorPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.key_dict = None
        self.results_cache = []
        self.last_analytical_matrix = None
        self.load_default_key()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30); layout.setSpacing(12)
        
        title = QLabel("<h2>🎯 Advanced Computer Vision Engine</h2>")
        layout.addWidget(title)
        
        ctrl_layout = QHBoxLayout()
        self.example_qs = QComboBox()
        self.example_qs.addItems(["50 Questions Architecture", "100 Questions Architecture"])
        
        self.slider_lbl = QLabel("Sensitivity Filter Threshold: 30%")
        self.ev_fill = QSlider(Qt.Horizontal)
        self.ev_fill.setRange(5, 80); self.ev_fill.setValue(30)
        self.ev_fill.valueChanged.connect(lambda v: self.slider_lbl.setText(f"Sensitivity Filter Threshold: {v}%"))
        
        ctrl_layout.addWidget(QLabel("Layout Mode:"))
        ctrl_layout.addWidget(self.example_qs)
        ctrl_layout.addWidget(self.slider_lbl)
        ctrl_layout.addWidget(self.ev_fill)
        layout.addLayout(ctrl_layout)
        
        actions_layout = QHBoxLayout()
        self.btn_key = QPushButton("Upload Master Key Mapping")
        self.btn_dl_key = QPushButton("Download Key Template")
        self.lbl_key = QLabel("Using factory fallback structural key patterns")
        self.lbl_key.setStyleSheet("color: orange; font-style: italic;")
        actions_layout.addWidget(self.btn_key)
        actions_layout.addWidget(self.btn_dl_key)
        actions_layout.addWidget(self.lbl_key)
        layout.addLayout(actions_layout)
        
        tabs_bar = QHBoxLayout()
        self.btn_tab_calib = QPushButton("Calibration & Analytical Matrix")
        self.btn_tab_batch = QPushButton("Batch Verification Workflow")
        tabs_bar.addWidget(self.btn_tab_calib); tabs_bar.addWidget(self.btn_tab_batch)
        layout.addLayout(tabs_bar)
        
        self.sub_stack = QStackedWidget()
        layout.addWidget(self.sub_stack)
        
        # PAGE A: CALIBRATION WORKSPACE
        self.page_calib = QWidget()
        pc_layout = QVBoxLayout(self.page_calib)
        
        pc_btn_layout = QHBoxLayout()
        self.btn_calib_scan = QPushButton("Select Scan Image for Matrix Testing")
        self.btn_save_calib_img = QPushButton("💾 Save Analytical Matrix Image (PNG)")
        self.btn_save_calib_img.setEnabled(False)
        pc_btn_layout.addWidget(self.btn_calib_scan)
        pc_btn_layout.addWidget(self.btn_save_calib_img)
        pc_layout.addLayout(pc_btn_layout)
        
        self.debug_txt = QLabel("Awaiting computer vision telemetry configuration...")
        self.debug_txt.setWordWrap(True)
        pc_layout.addWidget(self.debug_txt)
        
        img_display_row = QHBoxLayout()
        self.view_orig = QLabel("[Anchor Lock Display]")
        self.view_orig.setFixedSize(360, 360)
        self.view_orig.setStyleSheet("border: 1px dashed #cbd5e1; background: #f1f5f9;")
        self.view_orig.setAlignment(Qt.AlignCenter)
        
        self.view_warp = QLabel("[Matrix Alignment Display]")
        self.view_warp.setFixedSize(360, 360)
        self.view_warp.setStyleSheet("border: 1px dashed #cbd5e1; background: #f1f5f9;")
        self.view_warp.setAlignment(Qt.AlignCenter)
        
        img_display_row.addWidget(self.view_orig)
        img_display_row.addWidget(self.view_warp)
        pc_layout.addLayout(img_display_row)
        pc_layout.addStretch()
        
        # PAGE B: BATCH WORKSPACE
        self.page_batch = QWidget()
        pb_layout = QVBoxLayout(self.page_batch)
        
        batch_btns = QHBoxLayout()
        self.btn_batch_upload = QPushButton("Upload Multiple Scans Group")
        self.btn_batch_export = QPushButton("Export Aggregated CSV Report")
        self.btn_batch_export.setEnabled(False)
        batch_btns.addWidget(self.btn_batch_upload); batch_btns.addWidget(self.btn_batch_export)
        
        self.batch_prg = QProgressBar(); self.batch_prg.setVisible(False)
        self.batch_txt = QLabel("")
        
        self.table = QTableWidget(); self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "USN Target", "Name", "Course", "Version", "Status", 
            "Calculated Score", "Confidence Matrix", "Flagged Exceptions", "Needs Moderation"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        pb_layout.addLayout(batch_btns); pb_layout.addWidget(self.batch_prg)
        pb_layout.addWidget(self.batch_txt); pb_layout.addWidget(self.table)
        
        self.sub_stack.addWidget(self.page_calib); self.sub_stack.addWidget(self.page_batch)
        
        self.btn_tab_calib.clicked.connect(lambda: self.sub_stack.setCurrentIndex(0))
        self.btn_tab_batch.clicked.connect(lambda: self.sub_stack.setCurrentIndex(1))
        self.btn_key.clicked.connect(self.load_key_matrix)
        self.btn_dl_key.clicked.connect(self.download_key_template)
        self.btn_calib_scan.clicked.connect(self.run_calibration)
        self.btn_save_calib_img.clicked.connect(self.save_analytical_matrix_file)
        self.btn_batch_upload.clicked.connect(self.run_batch)
        self.btn_batch_export.clicked.connect(self.export_csv)

    def load_default_key(self):
        kd = {'A': {}, 'B': {}, 'C': {}, 'D': {}}
        for v in ['A', 'B', 'C', 'D']:
            kd[v] = {i: ['A', 'B', 'C', 'D'][(i-1) % 4] for i in range(1, 101)}
        self.key_dict = kd

    def download_key_template(self):
        save_path, _ = QFileDialog.getSaveFileName(self, "Download Key Template", "Master_Key_Template.csv", "CSV (*.csv)")
        if save_path:
            try:
                rows = []
                for i in range(1, 101):
                    rows.append({"Question": i, "Version_A": "A", "Version_B": "B", "Version_C": "C", "Version_D": "D"})
                pd.DataFrame(rows).to_csv(save_path, index=False)
                self.lbl_key.setText(f"✅ Template saved: {os.path.basename(save_path)}")
                self.lbl_key.setStyleSheet("color: green; font-weight: bold;")
            except Exception as e:
                self.lbl_key.setText(f"❌ Template saving fault: {str(e)}"); self.lbl_key.setStyleSheet("color: red;")

    def load_key_matrix(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Key Mapping Framework", "", "CSV Configuration Data (*.csv)")
        if path:
            try:
                df = pd.read_csv(path)
                kd = {'A': {}, 'B': {}, 'C': {}, 'D': {}}
                for _, row in df.iterrows():
                    q = int(row["Question"])
                    kd['A'][q] = str(row.get("Version_A", 'A')).strip().upper()
                    kd['B'][q] = str(row.get("Version_B", 'B')).strip().upper()
                    kd['C'][q] = str(row.get("Version_C", 'C')).strip().upper()
                    kd['D'][q] = str(row.get("Version_D", 'D')).strip().upper()
                self.key_dict = kd
                self.lbl_key.setText(f"✅ Key matrix active: {os.path.basename(path)}")
                self.lbl_key.setStyleSheet("color: green; font-weight: bold;")
            except Exception as e:
                self.lbl_key.setText(f"❌ Key format mismatch: {str(e)}"); self.lbl_key.setStyleSheet("color: red;")

    def run_calibration(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Telemetry Sheet", "", "Images/PDF (*.png *.jpg *.jpeg *.pdf)")
        if not path: return
        
        self.debug_txt.setText("⏳ Initializing Computer Vision pipeline parsing matrices...")
        cfg = CONFIG_50Q if "50" in self.example_qs.currentText() else CONFIG_100Q
        
        try:
            if path.lower().endswith('.pdf'):
                doc = fitz.open(path)
                pix = doc.load_page(0).get_pixmap(dpi=200)
                img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR) if pix.n == 4 else cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                doc.close()
            else:
                img = cv2.imread(path)
                
            if img is None: raise ValueError("Target bitstream vector payload unreadable.")
            
            res, orig_debug, warp_debug = evaluate_image(img, self.key_dict, self.ev_fill.value() / 100.0, cfg)
            
            self.display_matrix(orig_debug, self.view_orig)
            if warp_debug is not None:
                self.display_matrix(warp_debug, self.view_warp)
                self.last_analytical_matrix = warp_debug
                self.btn_save_calib_img.setEnabled(True)
            else:
                self.view_warp.setText("[Warp Missing]")
                self.btn_save_calib_img.setEnabled(False)
                
            log_metrics = f"<b>USN:</b> {res['USN']} | <b>Name:</b> {res['Name']} | <b>Course:</b> {res['Course']}<br><b>Score Vector:</b> {res['Score']} | <b>Confidence:</b> {res['Confidence']} | <b>Version:</b> {res['Version']}<br><b>Exception Diagnostics:</b> {res['Flagged Questions']}"
            self.debug_txt.setText(log_metrics)
        except Exception as e:
            self.debug_txt.setText(f"❌ Core processing failure: {str(e)}")

    def save_analytical_matrix_file(self):
        if self.last_analytical_matrix is not None:
            save_path, _ = QFileDialog.getSaveFileName(self, "Save Analytical Matrix Image", "Analytical_Matrix_Capture.png", "Images (*.png *.jpg *.jpeg)")
            if save_path:
                try:
                    cv2.imwrite(save_path, self.last_analytical_matrix)
                    self.debug_txt.setText(self.debug_txt.text() + "<br><span style='color:green;'><b>✅ Analytical matrix image successfully saved!</b></span>")
                except Exception as e:
                    self.debug_txt.setText(self.debug_txt.text() + f"<br><span style='color:red;'><b>❌ Failed to save image: {str(e)}</b></span>")

    def display_matrix(self, mat, target_label):
        rgb_img = cv2.cvtColor(mat, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_img.shape
        q_img = QImage(rgb_img.data, w, h, ch * w, QImage.Format_RGB888)
        pix = QPixmap.fromImage(q_img).scaled(target_label.width(), target_label.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        target_label.setPixmap(pix)

    def run_batch(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Select Scan Document Manifest", "", "Images/PDF Scans (*.png *.jpg *.jpeg *.pdf)")
        if not paths: return
        
        self.table.setRowCount(0); self.results_cache.clear()
        self.batch_prg.setVisible(True); self.batch_prg.setValue(0)
        self.btn_batch_upload.setEnabled(False)
        
        cfg = CONFIG_50Q if "50" in self.example_qs.currentText() else CONFIG_100Q
        
        self.batch_worker = EvaluationWorker(paths, self.key_dict, self.ev_fill.value(), cfg)
        self.batch_worker.progress_signal.connect(self.handle_batch_progress)
        self.batch_worker.row_signal.connect(self.handle_batch_row)
        self.batch_worker.finished_signal.connect(self.handle_batch_finished)
        self.batch_worker.start()

    def handle_batch_progress(self, current_count, text):
        self.batch_txt.setText(text)
        if self.batch_worker.paths:
            ratio = int((current_count / len(self.batch_worker.paths)) * 100)
            self.batch_prg.setValue(ratio)

    def handle_batch_row(self, row_data):
        self.results_cache.append(row_data)
        row_idx = self.table.rowCount()
        self.table.insertRow(row_idx)
        
        self.table.setItem(row_idx, 0, QTableWidgetItem(str(row_data.get("USN", "Error"))))
        self.table.setItem(row_idx, 1, QTableWidgetItem(str(row_data.get("Name", "Error"))))
        self.table.setItem(row_idx, 2, QTableWidgetItem(str(row_data.get("Course", "Error"))))
        self.table.setItem(row_idx, 3, QTableWidgetItem(str(row_data.get("Version", "N/A"))))
        self.table.setItem(row_idx, 4, QTableWidgetItem(str(row_data.get("Status", ""))))
        self.table.setItem(row_idx, 5, QTableWidgetItem(str(row_data.get("Score", 0))))
        self.table.setItem(row_idx, 6, QTableWidgetItem(str(row_data.get("Confidence", "0%"))))
        self.table.setItem(row_idx, 7, QTableWidgetItem(str(row_data.get("Flagged Questions", "None"))))
        self.table.setItem(row_idx, 8, QTableWidgetItem(str(row_data.get("Needs Moderation", "NO"))))

    def handle_batch_finished(self):
        self.batch_prg.setVisible(False)
        self.batch_txt.setText(f"✅ Processing completed successfully. Logged {len(self.results_cache)} sheets.")
        self.btn_batch_upload.setEnabled(True); self.btn_batch_export.setEnabled(True)

    def export_csv(self):
        if not self.results_cache: return
        save_path, _ = QFileDialog.getSaveFileName(self, "Export Evaluation Statistics", "OMR_Report_Manifest.csv", "Spreadsheets (*.csv)")
        if save_path:
            try:
                export_ordered_fields = ["USN", "Name", "Course", "Version", "Status", "Score", "Confidence", "Flagged Questions", "Needs Moderation"]
                df = pd.DataFrame(self.results_cache)
                df = df.reindex(columns=export_ordered_fields)
                df.to_csv(save_path, index=False)
                self.batch_txt.setText(f"✅ CSV Export written successfully to: {os.path.basename(save_path)}")
            except Exception as e:
                self.batch_txt.setText(f"❌ Export file permission fault: {str(e)}")

# ==============================================================================
# PART 5: MAIN WINDOW MANAGER
# ==============================================================================
class AMCExamSuiteMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AMC Exam Suite — Enterprise Edition")
        self.setGeometry(120, 120, 1200, 780)
        
        self.global_state = {"left_logo": None, "right_logo": None, "watermark": None, "students_df": None}
        
        central_widget = QWidget(); self.setCentralWidget(central_widget)
        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0); root_layout.setSpacing(0)
        
        self.sidebar = QListWidget(); self.sidebar.setFixedWidth(240)
        self.sidebar.addItems(["📖 Sheet Template Generator", "🎯 Computer Vision Evaluator"])
        
        self.viewport_stack = QStackedWidget()
        self.gen_panel = GeneratorPanel(self.global_state)
        self.eval_panel = EvaluatorPanel()
        
        self.viewport_stack.addWidget(self.gen_panel); self.viewport_stack.addWidget(self.eval_panel)
        root_layout.addWidget(self.sidebar); root_layout.addWidget(self.viewport_stack)
        
        self.sidebar.currentRowChanged.connect(self.viewport_stack.setCurrentIndex)
        self.sidebar.setCurrentRow(0)

# ==============================================================================
# PART 6: CORE THEMING APPLICATION BOOTSTRAPPER
# ==============================================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QMainWindow { background-color: #f8fafc; }
        QListWidget { background-color: #0f172a; color: #cbd5e1; font-size: 14px; border: none; }
        QListWidget::item { padding: 18px 14px; border-bottom: 1px solid #1e293b; }
        QListWidget::item:hover { background-color: #1e293b; }
        QListWidget::item:selected { background-color: #2563eb; color: white; font-weight: bold; }
        QStackedWidget { background-color: #ffffff; }
        QLabel { color: #334155; font-size: 13px; }
        QLineEdit, QComboBox { padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 5px; background-color: #ffffff; color: #1e293b; font-size: 13px; }
        QLineEdit:focus, QComboBox:focus { border: 1px solid #2563eb; }
        QPushButton { background-color: #e2e8f0; color: #0f172a; padding: 8px 16px; border-radius: 5px; font-weight: bold; font-size: 13px; border: 1px solid #cbd5e1; }
        QPushButton:hover { background-color: #cbd5e1; }
        QPushButton#PrimaryAction, QPushButton:hover#PrimaryAction { background-color: #2563eb; color: white; border: none; padding: 12px; }
        QPushButton:hover#PrimaryAction { background-color: #1d4ed8; }
        QTableWidget { background-color: #ffffff; border: 1px solid #e2e8f0; gridline-color: #e2e8f0; border-radius: 4px; }
        QHeaderView::section { background-color: #f1f5f9; padding: 6px; font-weight: bold; border: 1px solid #e2e8f0; }
        QSlider::groove:horizontal { height: 6px; background: #cbd5e1; border-radius: 3px; }
        QSlider::handle:horizontal { background: #2563eb; width: 14px; margin: -4px 0; border-radius: 7px; }
        QProgressBar { text-align: center; border: 1px solid #cbd5e1; border-radius: 4px; background: #f1f5f9; }
        QProgressBar::chunk { background-color: #2563eb; }
    """)
    suite_window = AMCExamSuiteMainWindow()
    suite_window.show()
    sys.exit(app.exec())
