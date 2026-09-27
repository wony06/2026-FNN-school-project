# -*- coding: utf-8 -*-
"""신뢰도 '높음' 트레이 요약을 다른 사람에게 보낼 수 있는 PDF 리포트로 만든다."""
import os, json
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                  Image, HRFlowable, KeepTogether)

PROJECT_DIR = r"C:\Users\ST-USER\Desktop\2026 학술제"
PHOTO_DIR = os.path.join(PROJECT_DIR, "menu_photos_web")
OUT_PATH = os.path.join(PROJECT_DIR, "높음_신뢰도_메뉴_3선.pdf")

# CID 표준폰트(MalgunBold 등)는 글자 모양을 임베드하지 않고 뷰어의 시스템폰트에 의존해서
# 렌더러에 따라 빈칸으로 나오는 경우가 있다 - 실제 TTF를 임베드해서 어떤 환경에서도 보이게 함.
pdfmetrics.registerFont(TTFont("Malgun", r"C:\Windows\Fonts\malgun.ttf"))
pdfmetrics.registerFont(TTFont("MalgunBold", r"C:\Windows\Fonts\malgunbd.ttf"))

ITEMS = [
    {"date": "2026-08-26", "shop": "105", "category": "양식", "photo": "2026-08-26_105_양식.jpg"},
    {"date": "2026-08-28", "shop": "105", "category": "양식", "photo": "2026-08-28_105_양식.jpg"},
    {"date": "2026-09-17", "shop": "105", "category": "양식", "photo": "2026-09-17_105_양식.jpg"},
]

with open(os.path.join(PROJECT_DIR, "month_lunch_trays.json"), encoding="utf-8") as f:
    trays = json.load(f)

by_key = {(r["date"], r["shop"], r["category"]): r for r in trays}

styles = getSampleStyleSheet()
title_style = ParagraphStyle("KTitle", parent=styles["Title"], fontName="MalgunBold",
                              fontSize=20, leading=26, alignment=TA_CENTER, spaceAfter=4)
subtitle_style = ParagraphStyle("KSubtitle", parent=styles["Normal"], fontName="Malgun",
                                 fontSize=10.5, leading=15, alignment=TA_CENTER, textColor=colors.HexColor("#555555"))
h2_style = ParagraphStyle("KH2", parent=styles["Heading2"], fontName="MalgunBold",
                           fontSize=15, leading=19, spaceBefore=4, spaceAfter=2)
meta_style = ParagraphStyle("KMeta", parent=styles["Normal"], fontName="Malgun",
                             fontSize=9.5, leading=13, textColor=colors.HexColor("#666666"))
note_style = ParagraphStyle("KNote", parent=styles["Normal"], fontName="Malgun",
                             fontSize=8.5, leading=12, textColor=colors.HexColor("#888888"))
cell_style = ParagraphStyle("KCell", parent=styles["Normal"], fontName="Malgun",
                             fontSize=9.5, leading=13)
cell_style_b = ParagraphStyle("KCellB", parent=styles["Normal"], fontName="MalgunBold",
                               fontSize=9.5, leading=13)

SHOP_LABEL = {"105": "학생식당", "401": "생활과학관식당", "204": "신소재공학관식당"}

doc = SimpleDocTemplate(OUT_PATH, pagesize=A4,
                         topMargin=20 * mm, bottomMargin=18 * mm,
                         leftMargin=20 * mm, rightMargin=20 * mm)

story = []
story.append(Paragraph("한양 트레이 — 신뢰도 \u201c높음\u201d 메뉴 3선", title_style))
story.append(Paragraph("2026년 8월 24일 ~ 9월 19일 중식 데이터 126개 트레이 중,<br/>미매칭·결측 없이 영양DB 매칭이 완전히 검증된 항목만 선별", subtitle_style))
story.append(Spacer(1, 6 * mm))
story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#cccccc")))
story.append(Spacer(1, 8 * mm))

NUT_ROWS = [
    ("열량", "kcal", "kcal"),
    ("탄수화물", "탄수화물_g", "g"),
    ("단백질", "단백질_g", "g"),
    ("지방", "지방_g", "g"),
    ("당류", "당류_g", "g"),
    ("나트륨", "나트륨_mg", "mg"),
    ("NRF6.3 지수", "NRF6.3", ""),
]

for i, it in enumerate(ITEMS):
    r = by_key[(it["date"], it["shop"], it["category"])]
    img_path = os.path.join(PHOTO_DIR, it["photo"])

    img = Image(img_path, width=75 * mm, height=56 * mm)
    img.hAlign = "LEFT"

    rows = []
    for label, key, unit in NUT_ROWS:
        val = r[key]
        val_str = f"{val:g}{unit}" if unit else f"{val:g}"
        rows.append([Paragraph(label, cell_style), Paragraph(val_str, cell_style_b)])

    nut_table = Table(rows, colWidths=[32 * mm, 32 * mm])
    nut_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#e5e5e5")),
    ]))

    header = Table([[img, nut_table]], colWidths=[80 * mm, 70 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))

    block = [
        Paragraph(r["main"], h2_style),
        Paragraph(
            f'{it["date"]} · {SHOP_LABEL[it["shop"]]} {it["category"]} · {r["price"]} · '
            f'1인분 제공량 {r["1인분_제공량_g"]:g}g · 신뢰도 {r["신뢰도"]}',
            meta_style),
        Spacer(1, 3 * mm),
        header,
        Spacer(1, 4 * mm),
        Paragraph(
            "표준 제공량(g) 기반 자동 추정치이며 실측값이 아닙니다. "
            "식약처 통합식품영양성분DB 기준으로 매칭·계산했습니다.",
            note_style),
    ]
    story.append(KeepTogether(block))
    if i < len(ITEMS) - 1:
        story.append(Spacer(1, 6 * mm))
        story.append(HRFlowable(width="100%", thickness=0.4, color=colors.HexColor("#e5e5e5")))
        story.append(Spacer(1, 6 * mm))

doc.build(story)
print(f"저장: {OUT_PATH}")
