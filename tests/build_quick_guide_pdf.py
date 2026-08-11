from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

BLUE = colors.HexColor("#225EA8")
TEXT = colors.HexColor("#172027")
MUTED = colors.HexColor("#64727C")
LIGHT = colors.HexColor("#F2F5F7")
BORDER = colors.HexColor("#D7DEE3")


def register_fonts() -> None:
    pdfmetrics.registerFont(TTFont("MSYH", r"C:\Windows\Fonts\msyh.ttc", subfontIndex=0))
    pdfmetrics.registerFont(TTFont("MSYH-Bold", r"C:\Windows\Fonts\msyhbd.ttc", subfontIndex=0))
    pdfmetrics.registerFont(TTFont("Consolas", r"C:\Windows\Fonts\consola.ttf"))
    pdfmetrics.registerFontFamily("MSYH", normal="MSYH", bold="MSYH-Bold")


def inline_markup(text: str) -> str:
    def render_link(match: re.Match[str]) -> str:
        label, target = match.groups()
        return label if label == target else f"{label}（{target}）"

    text = re.sub(r"\[([^]]+)\]\(([^)]+)\)", render_link, text)
    parts = re.split(r"(`[^`]*`)", text)
    rendered = []
    for part in parts:
        if part.startswith("`") and part.endswith("`"):
            value = html.escape(part[1:-1])
            rendered.append(f'<font name="MSYH" color="#184D7A">{value}</font>')
        else:
            rendered.append(html.escape(part))
    return "".join(rendered)


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleCN", parent=base["Title"], fontName="MSYH-Bold", fontSize=24,
            leading=32, textColor=TEXT, alignment=TA_LEFT, spaceAfter=5 * mm,
        ),
        "subtitle": ParagraphStyle(
            "SubtitleCN", parent=base["BodyText"], fontName="MSYH", fontSize=10.5,
            leading=18, textColor=MUTED, spaceAfter=7 * mm,
        ),
        "h2": ParagraphStyle(
            "H2CN", parent=base["Heading2"], fontName="MSYH-Bold", fontSize=15,
            leading=22, textColor=BLUE, spaceBefore=5 * mm, spaceAfter=2.5 * mm,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "BodyCN", parent=base["BodyText"], fontName="MSYH", fontSize=9.5,
            leading=16, textColor=TEXT, alignment=TA_LEFT, spaceAfter=2.4 * mm,
            wordWrap="CJK",
        ),
        "bullet": ParagraphStyle(
            "BulletCN", parent=base["BodyText"], fontName="MSYH", fontSize=9.3,
            leading=15.5, textColor=TEXT, leftIndent=5 * mm, firstLineIndent=-3.5 * mm,
            spaceAfter=1.5 * mm, wordWrap="CJK",
        ),
        "number": ParagraphStyle(
            "NumberCN", parent=base["BodyText"], fontName="MSYH", fontSize=9.3,
            leading=15.5, textColor=TEXT, leftIndent=7 * mm, firstLineIndent=-5 * mm,
            spaceAfter=1.5 * mm, wordWrap="CJK",
        ),
        "code": ParagraphStyle(
            "CodeCN", parent=base["Code"], fontName="MSYH", fontSize=8.7,
            leading=14.5, textColor=colors.HexColor("#24343F"), leftIndent=4 * mm,
            rightIndent=4 * mm, borderColor=BORDER, borderWidth=0.6,
            borderPadding=(3 * mm, 4 * mm, 3 * mm, 4 * mm), backColor=LIGHT,
            spaceBefore=1.5 * mm, spaceAfter=3 * mm, wordWrap="CJK",
        ),
        "table_header": ParagraphStyle(
            "TableHeaderCN", parent=base["BodyText"], fontName="MSYH-Bold",
            fontSize=8.8, leading=13, textColor=colors.white,
        ),
        "table_cell": ParagraphStyle(
            "TableCellCN", parent=base["BodyText"], fontName="MSYH",
            fontSize=8.5, leading=13, textColor=TEXT, wordWrap="CJK",
        ),
    }


def parse_table(lines: list[str], style: dict[str, ParagraphStyle], available_width: float) -> Table:
    rows = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        row_style = style["table_header"] if not rows else style["table_cell"]
        rows.append([Paragraph(inline_markup(cell), row_style) for cell in cells])
    columns = len(rows[0])
    widths = [available_width * (0.34 if i == 0 and columns == 2 else 1 / columns) for i in range(columns)]
    if columns == 2:
        widths[1] = available_width - widths[0]
    table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FA")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2.3 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.3 * mm),
    ]))
    return table


def build_story(markdown: str, available_width: float) -> list:
    style = styles()
    lines = markdown.splitlines()
    story = []
    index = 0
    if lines and lines[0].startswith("# "):
        story.append(Paragraph(inline_markup(lines[0][2:].strip()), style["title"]))
        index = 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index < len(lines) and not lines[index].startswith("#"):
        story.append(Paragraph(inline_markup(lines[index].strip()), style["subtitle"]))
        index += 1

    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("## "):
            story.append(Paragraph(inline_markup(line[3:]), style["h2"]))
            index += 1
            continue
        if line.startswith("```"):
            block = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                block.append(lines[index])
                index += 1
            index += 1
            content = "<br/>".join(html.escape(item) for item in block)
            story.append(Paragraph(content, style["code"]))
            continue
        if line.startswith("|"):
            block = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                block.append(lines[index].strip())
                index += 1
            story.append(KeepTogether([parse_table(block, style, available_width), Spacer(1, 3 * mm)]))
            continue
        bullet = re.match(r"^-\s+(.+)", line)
        if bullet:
            story.append(Paragraph("•  " + inline_markup(bullet.group(1)), style["bullet"]))
            index += 1
            continue
        number = re.match(r"^(\d+)\.\s+(.+)", line)
        if number:
            story.append(Paragraph(f"{number.group(1)}.  " + inline_markup(number.group(2)), style["number"]))
            index += 1
            continue
        story.append(Paragraph(inline_markup(line), style["body"]))
        index += 1
    return story


def page_frame(canvas, document) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 15 * mm, width - 18 * mm, 15 * mm)
    canvas.setFont("MSYH", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 10 * mm, "配音工具 v2.0 使用说明")
    canvas.drawRightString(width - 18 * mm, 10 * mm, f"第 {document.page} 页")
    if document.page > 1:
        canvas.line(18 * mm, height - 15 * mm, width - 18 * mm, height - 15 * mm)
        canvas.drawString(18 * mm, height - 11 * mm, "VOICE PRODUCTION WORKFLOW")
    canvas.restoreState()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    register_fonts()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    page_width, _ = A4
    left = right = 19 * mm
    document = SimpleDocTemplate(
        str(args.output), pagesize=A4, leftMargin=left, rightMargin=right,
        topMargin=20 * mm, bottomMargin=20 * mm,
        title="配音工具 v2.0 使用说明", author="Codex",
        subject="配音工作流快速操作说明",
    )
    markdown = args.source.read_text(encoding="utf-8-sig")
    story = build_story(markdown, page_width - left - right)
    document.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    print(args.output)


if __name__ == "__main__":
    main()
