import flet as ft
import pandas as pd
import cv2
import numpy as np
import fitz  # PyMuPDF
import io
import os
import itertools
import base64
import threading
import tkinter as tk
from tkinter import filedialog
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

# --- BYPASS STRICT COLLEGE SSL PROXY BLOCKS ---
import ssl
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass
# ----------------------------------------------

# Automatically create the dataset folder if it doesn't exist for ML Harvesting
DATASET_DIR = "omr_training_data/needs_review"
os.makedirs(DATASET_DIR, exist_ok=True)

# ==========================================
# PART 1: EXACT PDF GENERATOR LOGIC (MATH)
# ==========================================
DROPOUT_GREY = colors.Color(0.6, 0.6, 0.6)
OMR_PAGE_W, OMR_PAGE_H = A4
OMR_MARGIN = 10 * mm
OMR_CONTENT_W = OMR_PAGE_W - (2 * OMR_MARGIN)

def draw_official_header(c, width, y_top, left_logo, right_logo, college_name, is_caed=False, compact=False):
    c.saveState()
    if compact:
        logo_size = 18 * mm; font_main = 14; font_sub = 8; spacing = 4 * mm
    else:
        logo_size = 22 * mm; font_main = 16; font_sub = 9; spacing = 5 * mm

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
    c.drawCentredString(center_x, y_top, college_name)
    c.setFont("Helvetica", font_sub)
    c.drawCentredString(center_x, y_top - spacing, "AMC Campus, Bannerghatta Road, Bengaluru, Karnataka - 560083")
    c.drawCentredString(center_x, y_top - (2*spacing), "Autonomous Institution Affiliated to VTU, Belagavi")
    c.setFont("Helvetica-Bold", font_sub)
    c.drawCentredString(center_x, y_top - (3*spacing), "Approved by AICTE, New Delhi | NAAC A+ Accredited")
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
    c.saveState(); c.setStrokeColor(DROPOUT_GREY)
    box_w = 35 * mm; box_h = 6 * mm
    box_x = OMR_PAGE_W - OMR_MARGIN - box_w; box_y = omr_title_y - 1.5*mm 
    c.rect(box_x, box_y, box_w, box_h)
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 9)
    c.drawString(box_x - 16*mm, box_y + 1.5*mm, "Serial No:"); c.restoreState()
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
    qr_data = f"{usn}|{course_code}"
    qr_code = qr.QrCodeWidget(qr_data)
    bounds = qr_code.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    qr_size = 16 * mm
    d = Drawing(qr_size, qr_size, transform=[qr_size/width, 0, 0, qr_size/height, 0, 0])
    d.add(qr_code)
    renderPDF.draw(d, c, mid_x + 14.5*mm, y_bottom + 3*mm)
    return y_bottom - 2*mm 

def draw_omr_instructions_compact(c, y_start):
    box_h = 12 * mm 
    y_bottom = y_start - box_h
    c.saveState(); c.setStrokeColor(DROPOUT_GREY); c.rect(OMR_MARGIN, y_bottom, OMR_CONTENT_W, box_h); c.restoreState()
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 9)
    c.drawString(OMR_MARGIN + 3*mm, y_start - 4*mm, "INSTRUCTIONS TO STUDENTS")
    c.setFont("Helvetica", 7.5)
    c.drawString(OMR_MARGIN + 3*mm, y_start - 7.5*mm, "1. No extra marking on OMR sheet.")
    c.drawString(OMR_MARGIN + 55*mm, y_start - 7.5*mm, "3. Darken the circle completely.")
    c.drawString(OMR_MARGIN + 3*mm, y_start - 10.5*mm, "2. Use Black Ball Point Pen ONLY.")
    c.drawString(OMR_MARGIN + 55*mm, y_start - 10.5*mm, "4. Multiple markings are invalid.")
    mid_right_x = OMR_PAGE_W - OMR_MARGIN - 65*mm
    labels_y = y_start - 4.5*mm
    c.setFont("Helvetica-Bold", 7); c.drawString(mid_right_x, labels_y, "CORRECT:")
    c.saveState(); c.setFillColor(DROPOUT_GREY); c.circle(mid_right_x + 25*mm, labels_y + 1.5*mm, 3*mm, fill=1, stroke=0); c.restoreState()
    c.drawString(mid_right_x, labels_y - 6*mm, "WRONG:")
    gap = 10*mm; start_ex = mid_right_x + 20*mm; ex_y = labels_y - 6*mm + 1.5*mm 
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
    c.setFillColor(colors.black)
    c.rect(OMR_MARGIN + 5*mm, y_bottom + 2*mm, 4*mm, 4*mm, fill=1, stroke=0)
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 10)
    c.drawString(OMR_MARGIN + 15*mm, y_bottom + 2.8*mm, "Question Paper Version Code:")
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

def generate_batch_omr_pdf(college, left_logo, right_logo, watermark, students_data, course_code, exam_type, num_qs):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    for _, student in students_data.iterrows():
        usn = str(student.get('USN', student.iloc[0]))
        name = str(student.get('Name', student.iloc[1]))
        draw_omr_watermark(c, watermark)
        y_start = OMR_PAGE_H - 12*mm 
        curr_y = draw_official_header(c, OMR_PAGE_W, y_start, left_logo, right_logo, college)
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

def generate_caed_pdf(college, left_logo, right_logo):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4); margin = 5 * mm; content_w = width - 2*margin
    y_header_start = height - 10*mm
    header_bottom_y = draw_official_header(c, width, y_header_start, left_logo, right_logo, college, is_caed=True)
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
    x += col3; ex_w = col4 / 2; c.line(x+ex_w, footer_bottom_y, x+ex_w, footer_top_y); c.drawString(x+5*mm, footer_bottom_y + 5*mm, "Examiner 1"); c.drawString(x+ex_w+5*mm, footer_bottom_y + 5*mm, "Examiner 2")
    drawing_bottom = footer_top_y + 5*mm; drawing_height = drawing_top - drawing_bottom
    c.setLineWidth(1.5); c.rect(margin, drawing_bottom, content_w, drawing_height)
    c.showPage(); c.save(); buffer.seek(0)
    return buffer

def draw_diary_form(c, start_y, width, college, left_logo, right_logo):
    margin = 10 * mm; content_w = width - 2*margin
    y = draw_official_header(c, width, start_y, left_logo, right_logo, college, compact=True)
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

def generate_diary_pdf(college, left_logo, right_logo):
    buffer = io.BytesIO(); c = canvas.Canvas(buffer, pagesize=A4); width, height = A4
    draw_diary_form(c, height - 5*mm, width, college, left_logo, right_logo)
    c.setDash(3, 3); c.line(10*mm, height/2, width - 10*mm, height/2); c.setDash(1, 0)
    draw_diary_form(c, (height/2) - 5*mm, width, college, left_logo, right_logo)
    c.showPage(); c.save(); buffer.seek(0)
    return buffer

# ==========================================
# PART 2: EXACT CV EVALUATOR LOGIC (MATH)
# ==========================================
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
    
    return best_corners, thresh, gray, version_anchor, warped_thresh, warped_color

def evaluate_image(image, multi_master_key, fill_percentage, config):
    flagged_log = []
    res = find_anchors_and_warp(image, config)
    
    if res[0] == "TOO_DARK":
        return {"USN": "Error", "Course": "Error", "Version": "N/A", "Score": 0, "Confidence": "0%", "Needs Moderation": "YES", "Flagged Questions": "Invalid Scan (Dark)", "Status": "Scan rejected: Image too dark."}, image.copy(), None
    if res[0] is None:
        return {"USN": "Error", "Course": "Error", "Version": "N/A", "Score": 0, "Confidence": "0%", "Needs Moderation": "YES", "Flagged Questions": "Failed mapping", "Status": "Failed to map 4 perfect corners."}, image.copy(), None

    corners, thresh, gray, version_anchor, warped_thresh, warped_color = res
    qr_data = None
    h, w = gray.shape
    
    if len(gray.shape) > 2:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
        
    top_right_gray = gray[0:int(h*0.35), int(w*0.5):w]
    tr_large = cv2.resize(top_right_gray, (0,0), fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    tr_thresh = cv2.threshold(tr_large, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

    try:
        from pyzbar.pyzbar import decode
        decoded = decode(tr_large)
        if decoded: qr_data = decoded[0].data.decode('utf-8')
        if not qr_data:
            decoded = decode(tr_thresh)
            if decoded: qr_data = decoded[0].data.decode('utf-8')
    except ImportError: pass 

    if not qr_data:
        qr_detector = cv2.QRCodeDetector()
        qr_data, _, _ = qr_detector.detectAndDecode(tr_large)
        if not qr_data: qr_data, _, _ = qr_detector.detectAndDecode(tr_thresh)
        if not qr_data: qr_data, _, _ = qr_detector.detectAndDecode(gray) 

    usn, course_code = "Unknown", "Unknown"
    if qr_data and '|' in qr_data: usn, course_code = qr_data.split('|')

    debug_original = image.copy()
    for c in corners: cv2.circle(debug_original, (int(c['x']), int(c['y'])), 20, (0, 255, 255), 4)
    if version_anchor: cv2.rectangle(debug_original, (int(version_anchor['x'])-15, int(version_anchor['y'])-15), (int(version_anchor['x'])+15, int(version_anchor['y'])+15), (255, 0, 255), 4)

    detected_version, flags_count, needs_moderation = "N/A", 0, "NO"
    if version_anchor is not None:
        global_scale = np.sqrt((corners[1]['x'] - corners[0]['x'])**2 + (corners[1]['y'] - corners[0]['y'])**2) / (config['warped_w'] / 10.0) 
        b_start_x, b_spacing, b_rad = version_anchor['x'] + (68 * global_scale), 11 * global_scale, int(3.2 * global_scale)      
        b_area = 3.1415 * (b_rad ** 2)
        v_fills = []
        for i, opt in enumerate(['A', 'B', 'C', 'D']):
            cx, cy = int(b_start_x + (i * b_spacing)), int(version_anchor['y'])
            cv2.circle(debug_original, (cx, cy), b_rad, (255, 0, 0), 2)
            mask = np.zeros(thresh.shape, dtype="uint8")
            cv2.circle(mask, (cx, cy), b_rad, 255, -1)
            v_fills.append((cv2.countNonZero(cv2.bitwise_and(thresh, thresh, mask=mask)) / b_area, i))
        v_fills.sort(key=lambda x: x[0], reverse=True)
        if v_fills[0][0] > fill_percentage: detected_version = ['A', 'B', 'C', 'D'][v_fills[0][1]]
        else:
            detected_version = "Blank"; flags_count += 1; needs_moderation = "YES"; flagged_log.append("Version Code (Unclear)")

    actual_score, final_status = 0, "Evaluated Successfully"
    active_key = multi_master_key.get(detected_version, {}) if detected_version in ['A', 'B', 'C', 'D'] else multi_master_key.get('A', {})
    if detected_version not in ['A', 'B', 'C', 'D']: final_status = "Warning: Version Code Invalid."

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
                cv2.circle(warped_color, (bx, by), config['b_radius'], (255, 0, 0), 2)
                mask = np.zeros(warped_thresh.shape, dtype="uint8")
                cv2.circle(mask, (bx, by), config['b_radius'], 255, -1)
                fills.append((cv2.countNonZero(cv2.bitwise_and(warped_thresh, warped_thresh, mask=mask)) / bubble_area, i))
                
            fills.sort(key=lambda x: x[0], reverse=True)
            ans, is_confident = "Blank", True
            if fills[0][0] > fill_percentage:
                if fills[1][0] > fill_percentage: ans, is_confident = "Multiple", False 
                else: ans = ['A', 'B', 'C', 'D'][fills[0][1]]
            else: is_confident = False
                
            if not is_confident or ans in ["Multiple", "Blank"]:
                flags_count += 1; needs_moderation = "YES"
                flagged_log.append(f"Q{q_current} (Multiple)" if ans == "Multiple" else f"Q{q_current} (Blank/Light)")
                y1, y2 = max(0, int(curr_y - config['b_radius'] * 2.5)), min(warped_color.shape[0], int(curr_y + config['b_radius'] * 2.5))
                x1, x2 = max(0, int(b_start_x - config['b_radius'] * 2)), min(warped_color.shape[1], int(b_start_x + (4 * config['b_spacing']) + config['b_radius']))
                crop_img = warped_color[y1:y2, x1:x2] 
                if crop_img.size > 0: cv2.imwrite(os.path.join(DATASET_DIR, f"{usn}_Q{q_current}_guess_{ans}.jpg"), crop_img)

            if active_key and ans == active_key.get(q_current): actual_score += 1
            curr_y += config['row_h']; q_current += 1

    return {
        "USN": usn, "Course": course_code, "Version": detected_version, "Score": actual_score, 
        "Confidence": f"{max(0, 100 - (flags_count * 2))}%", "Needs Moderation": needs_moderation,
        "Flagged Questions": ", ".join(flagged_log) if flagged_log else "None", "Status": final_status
    }, debug_original, warped_color

def cv2_to_base64(img):
    _, buffer = cv2.imencode('.png', img)
    return base64.b64encode(buffer).decode('utf-8')


# ==========================================
# PART 3: NATIVE TKINTER DIALOG WRAPPERS
# ==========================================
def _open_file_dialog(title, filetypes, callback):
    def run_dialog():
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes('-topmost', 1)
        file_path = filedialog.askopenfilename(title=title, filetypes=filetypes)
        root.destroy()
        callback(file_path)
    threading.Thread(target=run_dialog, daemon=True).start()

def _open_files_dialog(title, filetypes, callback):
    def run_dialog():
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes('-topmost', 1)
        file_paths = filedialog.askopenfilenames(title=title, filetypes=filetypes)
        root.destroy()
        callback(list(file_paths) if file_paths else [])
    threading.Thread(target=run_dialog, daemon=True).start()

def _save_file_dialog(title, defaultextension, filetypes, initialfile, callback):
    def run_dialog():
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes('-topmost', 1)
        file_path = filedialog.asksaveasfilename(title=title, defaultextension=defaultextension, filetypes=filetypes, initialfile=initialfile)
        root.destroy()
        callback(file_path)
    threading.Thread(target=run_dialog, daemon=True).start()


# ==========================================
# PART 4: THE FLET DESKTOP UI
# ==========================================
def main(page: ft.Page):
    page.title = "AMC Exam Suite"
    page.theme_mode = "light" 
    page.padding = 20
    page.scroll = "auto" 

    # --- STATE MANAGEMENT ---
    gen_state = {"left_logo": None, "right_logo": None, "watermark": None, "students_df": None}
    eval_state = {"key_dict": None, "results": []}

    def load_default_key():
        kd = {'A': {}, 'B': {}, 'C': {}, 'D': {}}
        for v in ['A', 'B', 'C', 'D']:
            kd[v] = {i: ['A', 'B', 'C', 'D'][(i-1) % 4] for i in range(1, 101)}
        eval_state["key_dict"] = kd
    load_default_key()

    # --- GENERATOR COMPONENTS (DEFENSIVE INSTANTIATION) ---
    format_dropdown = ft.Dropdown(
        label="Select Sheet Format",
        options=[ft.dropdown.Option("OMR Answer Sheet"), ft.dropdown.Option("CAED Printout Sheet"), ft.dropdown.Option("Relieving Superintendent Diary")],
        value="OMR Answer Sheet", width=400)
    college_name = ft.TextField(label="College Name", value="AMC ENGINEERING COLLEGE", width=400)
    exam_type = ft.TextField(label="Exam Type", value="SEMESTER END EXAMINATION", width=400)
    course_code = ft.TextField(label="Course Code", value="1BENG206", width=400)
    num_qs_dropdown = ft.Dropdown(label="Number of Questions", options=[ft.dropdown.Option("50"), ft.dropdown.Option("100")], value="100", width=400)
    
    lbl_left = ft.Text("No left logo selected.", italic=True, size=12)
    lbl_right = ft.Text("No right logo selected.", italic=True, size=12)
    lbl_watermark = ft.Text("No watermark selected.", italic=True, size=12)
    lbl_csv = ft.Text("No CSV loaded.", italic=True, size=12, color="red700") 
    
    gen_status_text = ft.Text("", weight="bold", size=16)

    # NO KWARGS ALLOWED IN TEXT ARGUMENTS!
    gen_btn = ft.ElevatedButton("Generate PDF Document", icon="picture_as_pdf")
    btn_upload_left = ft.ElevatedButton("Upload Left Logo", icon="image")
    btn_upload_right = ft.ElevatedButton("Upload Right Logo", icon="image")
    btn_upload_watermark = ft.ElevatedButton("Upload Watermark", icon="water_drop")
    btn_upload_csv = ft.ElevatedButton("Upload Student CSV", icon="table_view")


    # --- EVALUATOR COMPONENTS (DEFENSIVE INSTANTIATION) ---
    ev_qs = ft.Dropdown(options=[ft.dropdown.Option("50"), ft.dropdown.Option("100")], value="100", width=200)
    ev_fill = ft.Slider(min=10, max=80, divisions=14, value=30)
    ev_key_lbl = ft.Text("No key uploaded. Using default pattern.", color="orange", italic=True)

    # Empty instantiation, assign properties after to bypass __init__ versioning crash
    img_orig = ft.Image()
    img_orig.width = 350
    img_orig.height = 350
    img_orig.fit = "contain"
    img_orig.visible = False

    img_warp = ft.Image()
    img_warp.width = 350
    img_warp.height = 350
    img_warp.fit = "contain"
    img_warp.visible = False

    debug_txt = ft.Text("Upload a scan to begin.", size=14)

    # NO KWARGS ALLOWED IN TEXT ARGUMENTS!
    btn_ev_key = ft.ElevatedButton("Upload Master Key", icon="key")
    btn_ev_calib = ft.ElevatedButton("Upload Scan for Testing", icon="upload")
    btn_batch_upload = ft.ElevatedButton("Upload Batch Scans", icon="dynamic_feed")
    btn_batch_export = ft.ElevatedButton("Download CSV Report", icon="download")
    btn_batch_export.disabled = True

    btn_tab_calib = ft.ElevatedButton("📐 Calibration Debugger", data="calib")
    btn_tab_batch = ft.ElevatedButton("🚀 Batch Processing", data="batch")

    batch_prg = ft.ProgressBar(width=400, value=0, visible=False)
    batch_txt = ft.Text("")
    
    dt_columns = [ft.DataColumn(ft.Text(x)) for x in ["USN", "Score", "Conf", "Flags", "File"]]
    dt = ft.DataTable(columns=dt_columns, rows=[])

    # ---------------------------------------------------------
    # UI HANDLER FUNCTIONS
    # ---------------------------------------------------------
    
    def pick_left(e):
        def on_selected(path):
            if path:
                gen_state["left_logo"] = path
                lbl_left.value = f"Selected: {os.path.basename(path)}"
                page.update()
        _open_file_dialog("Select Left Logo", [("Images", "*.png *.jpg *.jpeg")], on_selected)
    btn_upload_left.on_click = pick_left

    def pick_right(e):
        def on_selected(path):
            if path:
                gen_state["right_logo"] = path
                lbl_right.value = f"Selected: {os.path.basename(path)}"
                page.update()
        _open_file_dialog("Select Right Logo", [("Images", "*.png *.jpg *.jpeg")], on_selected)
    btn_upload_right.on_click = pick_right

    def pick_watermark(e):
        def on_selected(path):
            if path:
                gen_state["watermark"] = path
                lbl_watermark.value = f"Selected: {os.path.basename(path)}"
                page.update()
        _open_file_dialog("Select Watermark", [("Images", "*.png *.jpg *.jpeg")], on_selected)
    btn_upload_watermark.on_click = pick_watermark

    def pick_csv(e):
        def on_selected(path):
            if path:
                try:
                    gen_state["students_df"] = pd.read_csv(path)
                    lbl_csv.value = f"Loaded {len(gen_state['students_df'])} students."
                    lbl_csv.color = "green700" 
                except Exception as ex:
                    lbl_csv.value = f"Error reading CSV: {ex}"
                    lbl_csv.color = "red700" 
                page.update()
        _open_file_dialog("Select Student CSV", [("CSV Files", "*.csv")], on_selected)
    btn_upload_csv.on_click = pick_csv

    def trigger_generate_save(e):
        fmt = format_dropdown.value
        col = college_name.value
        crs = course_code.value
        exam = exam_type.value
        qs = int(num_qs_dropdown.value)

        default_name = "AMC_CAED.pdf"
        if fmt == "Relieving Superintendent Diary": default_name = "AMC_Relieving_Diary.pdf"
        elif fmt == "OMR Answer Sheet": default_name = f"AMC_OMR_{crs}_{qs}Q_Batch.pdf"

        def on_save_path(save_path):
            if not save_path: return

            gen_btn.disabled = True
            gen_btn.text = "⏳ Generating PDF..."
            gen_status_text.value = "Processing data and rendering document. Please wait..."
            gen_status_text.color = "blue700"
            page.update()

            def background_generate():
                try:
                    if fmt == "CAED Printout Sheet":
                        pdf_buf = generate_caed_pdf(col, gen_state["left_logo"], gen_state["right_logo"])
                    elif fmt == "Relieving Superintendent Diary":
                        pdf_buf = generate_diary_pdf(col, gen_state["left_logo"], gen_state["right_logo"])
                    else: 
                        if gen_state["students_df"] is None:
                            gen_status_text.value = "❌ Cannot generate OMR: Please upload a Student CSV first."
                            gen_status_text.color = "red700" 
                            return
                        pdf_buf = generate_batch_omr_pdf(col, gen_state["left_logo"], gen_state["right_logo"], gen_state["watermark"], gen_state["students_df"], crs, exam, qs)
                    
                    with open(save_path, "wb") as f:
                        f.write(pdf_buf.getbuffer())
                    
                    gen_status_text.value = f"✅ Saved successfully to: {os.path.basename(save_path)}"
                    gen_status_text.color = "green700" 
                except Exception as ex:
                    gen_status_text.value = f"❌ Generation Error: {ex}"
                    gen_status_text.color = "red700" 
                finally:
                    gen_btn.disabled = False
                    gen_btn.text = "Generate PDF Document"
                    page.update()

            threading.Thread(target=background_generate, daemon=True).start()
            
        _save_file_dialog("Save PDF Document", ".pdf", [("PDF Files", "*.pdf")], default_name, on_save_path)
    gen_btn.on_click = trigger_generate_save

    # Evaluator Handlers
    def pick_ev_key(e):
        def on_selected(path):
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
                    eval_state["key_dict"] = kd
                    ev_key_lbl.value = f"✅ Key Loaded: {os.path.basename(path)}"
                    ev_key_lbl.color = "green"
                except Exception as ex:
                    ev_key_lbl.value = f"Error: {ex}"
                    ev_key_lbl.color = "red"
                page.update()
        _open_file_dialog("Select Master Key CSV", [("CSV Files", "*.csv")], on_selected)
    btn_ev_key.on_click = pick_ev_key

    def pick_ev_calib(e):
        def on_path_selected(path):
            if not path: return

            debug_txt.value = "⏳ Analyzing Scan... please wait."
            img_orig.visible = False
            img_warp.visible = False
            page.update()

            def background_calib():
                cfg = CONFIG_50Q if ev_qs.value == "50" else CONFIG_100Q
                try:
                    if path.lower().endswith('.pdf'):
                        doc = fitz.open(path)
                        pix = doc.load_page(0).get_pixmap(dpi=200)
                        img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                        if pix.n == 4: img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)
                        elif pix.n == 3: img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                        elif pix.n == 1: img_array = cv2.cvtColor(img_array, cv2.COLOR_GRAY2BGR)
                        doc.close()
                    else:
                        img_array = cv2.imread(path)
                    
                    if img_array is None:
                        debug_txt.value = "❌ Error: Could not read image/PDF file."
                        page.update(); return

                    res, d_orig, d_warp = evaluate_image(img_array, eval_state["key_dict"], ev_fill.value/100.0, cfg)
                    debug_txt.value = f"✅ Analysis Complete\n\nUSN: {res['USN']}\nScore: {res['Score']}\nConfidence: {res['Confidence']}\nFlagged: {res['Flagged Questions']}"
                    
                    if d_orig is not None: 
                        img_orig.src_base64 = cv2_to_base64(d_orig)
                        img_orig.visible = True
                    if d_warp is not None: 
                        img_warp.src_base64 = cv2_to_base64(d_warp)
                        img_warp.visible = True
                except Exception as ex:
                    debug_txt.value = f"❌ Analysis Error: {ex}"
                
                page.update()

            threading.Thread(target=background_calib, daemon=True).start()
        _open_file_dialog("Select Scan for Testing", [("Images/PDFs", "*.jpg *.jpeg *.png *.pdf")], on_path_selected)
    btn_ev_calib.on_click = pick_ev_calib

    def pick_ev_batch(e):
        def on_paths_selected(paths):
            if not paths: return

            btn_batch_upload.disabled = True
            btn_batch_export.disabled = True
            batch_prg.visible = True
            batch_prg.value = 0
            eval_state["results"] = []
            dt.rows.clear()
            page.update()

            def background_batch():
                total_items = len(paths)
                cfg = CONFIG_50Q if ev_qs.value == "50" else CONFIG_100Q
                
                for idx, path in enumerate(paths):
                    filename = os.path.basename(path)
                    batch_txt.value = f"Processing {idx+1}/{total_items}: {filename}"
                    batch_prg.value = (idx+1)/total_items
                    page.update()
                    
                    try:
                        if path.lower().endswith('.pdf'):
                            doc = fitz.open(path)
                            for p_num in range(len(doc)):
                                pix = doc.load_page(p_num).get_pixmap(dpi=200)
                                img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                                if pix.n == 4: img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
                                elif pix.n == 3: img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                                elif pix.n == 1: img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                                res, _, _ = evaluate_image(img, eval_state["key_dict"], ev_fill.value/100.0, cfg)
                                res["File Name"] = f"{filename} (Pg {p_num+1})"
                                eval_state["results"].append(res)
                            doc.close()
                        else:
                            img = cv2.imread(path)
                            if img is not None:
                                res, _, _ = evaluate_image(img, eval_state["key_dict"], ev_fill.value/100.0, cfg)
                                res["File Name"] = filename
                                eval_state["results"].append(res)
                            else:
                                eval_state["results"].append({"USN": "Error", "Score": 0, "Confidence": "0%", "Flagged Questions": "Unreadable File", "File Name": filename})
                    except Exception as ex:
                        eval_state["results"].append({"USN": "Error", "Score": 0, "Confidence": "0%", "Flagged Questions": f"Crash: {ex}", "File Name": filename})
                
                for r in eval_state["results"]:
                    dt.rows.append(ft.DataRow(cells=[
                        ft.DataCell(ft.Text(str(r.get("USN", "Error")))), 
                        ft.DataCell(ft.Text(str(r.get("Score", 0)))), 
                        ft.DataCell(ft.Text(str(r.get("Confidence", "0%")))), 
                        ft.DataCell(ft.Text(str(r.get("Flagged Questions", "")))), 
                        ft.DataCell(ft.Text(str(r.get("File Name", ""))))
                    ]))
                
                batch_prg.visible = False
                batch_txt.value = f"✅ Batch Complete! Processed {total_items} files."
                btn_batch_upload.disabled = False
                btn_batch_export.disabled = False
                page.update()

            threading.Thread(target=background_batch, daemon=True).start()
        _open_files_dialog("Select Batch Scans", [("Images/PDFs", "*.jpg *.jpeg *.png *.pdf")], on_paths_selected)
    btn_batch_upload.on_click = pick_ev_batch

    def save_ev_export(e):
        def on_save_path(path):
            if path and eval_state["results"]:
                pd.DataFrame(eval_state["results"])[["USN", "Course", "Version", "Score", "Confidence", "Needs Moderation", "Flagged Questions", "Status", "File Name"]].to_csv(path, index=False)
                batch_txt.value = f"✅ Exported to {path}"
                page.update()
        _save_file_dialog("Save CSV Report", ".csv", [("CSV Files", "*.csv")], "AMC_Evaluation_Report.csv", on_save_path)
    btn_batch_export.on_click = save_ev_export


    # ---------------------------------------------------------
    # LAYOUT CONSTRUCTION
    # ---------------------------------------------------------
    def on_format_change(e):
        omr_settings.visible = (format_dropdown.value == "OMR Answer Sheet")
        page.update()
    format_dropdown.on_change = on_format_change

    general_settings = ft.Column(controls=[
        ft.Text("1. General Settings", size=18, weight="bold"),
        format_dropdown,
        college_name,
        ft.Row(controls=[btn_upload_left, lbl_left]),
        ft.Row(controls=[btn_upload_right, lbl_right]),
    ], spacing=15)

    omr_settings = ft.Column(controls=[
        ft.Divider(),
        ft.Text("2. OMR Specific Settings", size=18, weight="bold"),
        exam_type,
        course_code,
        num_qs_dropdown,
        ft.Row(controls=[btn_upload_watermark, lbl_watermark]),
        ft.Row(controls=[btn_upload_csv, lbl_csv]),
        ft.Text("CSV Format Note: File must contain headers 'USN' and 'Name'", italic=True, size=12)
    ], spacing=15)

    generator_content = ft.Column(controls=[
        ft.Text("📄 AMC Exam Sheet Generator", size=28, weight="bold"), ft.Divider(),
        ft.Row(controls=[
            general_settings, ft.Container(width=50), omr_settings
        ]),
        ft.Divider(),
        gen_btn, 
        gen_status_text
    ])

    eval_general = ft.Column(controls=[
        ft.Text("1. Evaluation Settings", size=18, weight="bold"),
        ft.Row(controls=[ev_qs, ft.Text("Ink Threshold (Confidence):"), ev_fill]),
        ft.Row(controls=[btn_ev_key, ev_key_lbl])
    ], spacing=15)

    eval_debug = ft.Column(controls=[
        ft.Divider(),
        ft.Text("2. Single Scan Calibration", size=18, weight="bold"),
        ft.Row(controls=[btn_ev_calib]),
        ft.Row(controls=[
            ft.Column(controls=[ft.Text("Metrics", weight="bold"), debug_txt], width=200),
            ft.Column(controls=[ft.Text("Corner Lock", weight="bold"), img_orig]),
            ft.Column(controls=[ft.Text("Math Grid", weight="bold"), img_warp])
        ])
    ], spacing=15)

    # REMOVED border kwargs from container to bypass flet border alias crash
    eval_batch = ft.Column(controls=[
        ft.Divider(),
        ft.Text("3. Batch Processing", size=18, weight="bold"),
        ft.Row(controls=[btn_batch_upload, btn_batch_export]),
        batch_prg, batch_txt, 
        ft.Container(content=ft.Column(controls=[dt], scroll="auto"), height=400)
    ], spacing=15, visible=False)

    def switch_eval_tab(e):
        if e.control.data == "calib":
            eval_debug.visible = True
            eval_batch.visible = False
        elif e.control.data == "batch":
            eval_debug.visible = False
            eval_batch.visible = True
        page.update()
        
    btn_tab_calib.on_click = switch_eval_tab
    btn_tab_batch.on_click = switch_eval_tab

    evaluator_content = ft.Column(controls=[
        ft.Text("🎯 OMR Evaluator", size=28, weight="bold"), ft.Divider(),
        eval_general, ft.Divider(),
        ft.Row(controls=[btn_tab_calib, btn_tab_batch]),
        eval_debug, eval_batch
    ])

    view_container = ft.Container(content=generator_content)

    def switch_main_view(e): 
        if e.control.data == "gen":
            view_container.content = generator_content
        else:
            view_container.content = evaluator_content
        page.update()

    btn_nav_gen = ft.ElevatedButton("📄 Generator", data="gen", width=200, height=50)
    btn_nav_eval = ft.ElevatedButton("🎯 Evaluator", data="eval", width=200, height=50)
    btn_nav_gen.on_click = switch_main_view
    btn_nav_eval.on_click = switch_main_view

    page.add(ft.Column(controls=[
        ft.Row(controls=[btn_nav_gen, btn_nav_eval]),
        ft.Divider(),
        view_container
    ]))

# NOTE: run() is the new standard instead of app()
if __name__ == "__main__":
    ft.run(main)
