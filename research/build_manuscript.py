#!/usr/bin/env python3
"""Build manuscript HTML and LaTeX from docs/MANUSCRIPT.md.

The HTML is the print-ready source used for the checked PDF. PDF generation is
optional and uses installed Microsoft Edge in headless print mode.
"""
from __future__ import annotations

import argparse
import html
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "MANUSCRIPT.md"
HTML_OUT = ROOT / "docs" / "MANUSCRIPT.html"
TEX_OUT = ROOT / "docs" / "manuscript_latex" / "main.tex"
PDF_OUT = ROOT / "docs" / "manuscript_latex" / "SemanticSync-Manuscript.pdf"

# The canonical Markdown reference list is numbered for readability. This map
# keeps its citations connected to stable keys in the extensible BibTeX file.
REFERENCE_KEYS = {
    1: "balegas2015", 2: "balegas2018", 3: "spanner2013", 4: "dynamo2007",
    5: "edwards2023", 6: "gomes2017", 7: "kleppmann2017json",
    8: "localfirst2019", 9: "kulkarni2014hlc", 10: "lewchenko2018",
    11: "shapiro2011", 12: "crsqlite", 13: "electricsql", 14: "synql2024",
    15: "crdv2025", 16: "thomassen2023", 17: "antidotesql2018",
    18: "schiefer2022", 19: "conloc2025", 20: "lore2024", 21: "borrego2025",
    22: "riffle2023", 23: "tomter2021", 24: "bauwens2023", 25: "removewin2021",
    26: "crust2025",
}


def inline_html(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^ )]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\$([^$]+)\$", r'<span class="math">\1</span>', text)
    return text


def inline_tex(text: str) -> str:
    # Preserve explicit math spans while escaping prose and code safely.
    citation_tokens: dict[str, str] = {}

    def citation(match: re.Match[str]) -> str:
        numbers = [int(value.strip()) for value in match.group(1).split(",")]
        missing = [number for number in numbers if number not in REFERENCE_KEYS]
        if missing:
            raise ValueError(f"Citation number(s) missing from REFERENCE_KEYS: {missing}")
        token = f"SEMANTICSYNCCITATION{len(citation_tokens)}END"
        citation_tokens[token] = r"\cite{" + ",".join(REFERENCE_KEYS[number] for number in numbers) + "}"
        return token

    text = re.sub(r"\[(\d+(?:\s*,\s*\d+)*)\]", citation, text)
    pieces = re.split(r"(\$[^$]+\$|`[^`]+`|\[[^\]]+\]\(https?://[^ )]+\))", text)
    out: list[str] = []
    for piece in pieces:
        if not piece:
            continue
        if piece.startswith("$") and piece.endswith("$"):
            out.append("$" + piece[1:-1] + "$")
        elif piece.startswith("`") and piece.endswith("`"):
            value = piece[1:-1].replace("}", "\\} ").replace("{", "\\{")
            out.append(r"\texttt{\detokenize{" + value + "}}")
        elif piece.startswith("["):
            match = re.fullmatch(r"\[([^\]]+)\]\((https?://[^ )]+)\)", piece)
            if match:
                out.append(r"\href{" + match.group(2) + "}{" + inline_tex(match.group(1)) + "}")
        else:
            value = piece
            for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}")):
                value = value.replace(a, b)
            value = re.sub(r"\*\*([^*]+)\*\*", r"\\textbf{\1}", value)
            value = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\\emph{\1}", value)
            out.append(value)
    rendered = "".join(out)
    for token, command in citation_tokens.items():
        rendered = rendered.replace(token, command)
    return rendered


def is_table_row(line: str) -> bool:
    return line.strip().startswith("|") and line.strip().endswith("|")


def architecture_svg() -> str:
    groups = [
        (12, 278, "Client replicas", ["Application / client UI", "SQLite driver", "Local SQLite database", "Supported tracked writes"]),
        (312, 318, "SemanticSync engine", ["Schema inspector + validator", "Three-way conflict detector", "Semantic policy resolver", "Foreign-key quarantine", "HLC metadata", "Checkpoint / compaction"]),
        (648, 240, "Sync services", ["Base ancestor store", "Checkpoint manifest store", "FastAPI sync reconciler"]),
    ]
    out = ['<svg class="architecture" role="img" aria-labelledby="arch-title arch-desc" viewBox="0 0 900 228" xmlns="http://www.w3.org/2000/svg"><title id="arch-title">SemanticSync system architecture</title><desc id="arch-desc">Three replica, engine, and sync-service groups with data flow from replicas through the engine to sync services.</desc>']
    for x, width, title, labels in groups:
        out.append(f'<rect x="{x}" y="8" width="{width}" height="210" rx="10" fill="#f5f8fa" stroke="#9aabba"/>')
        out.append(f'<text x="{x+14}" y="31" class="arch-head">{html.escape(title)}</text>')
        y = 42
        for label in labels:
            out.append(f'<rect x="{x+12}" y="{y}" width="{width-24}" height="23" rx="4" fill="#fff" stroke="#c6d1da"/>')
            out.append(f'<text x="{x+20}" y="{y+16}" class="arch-label">{html.escape(label)}</text>')
            y += 27
    out += ['<path d="M292 112 H307" stroke="#55758f" stroke-width="2" marker-end="url(#arrow)"/>', '<path d="M630 112 H643" stroke="#55758f" stroke-width="2" marker-end="url(#arrow)"/>', '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="#55758f"/></marker></defs></svg>']
    return "".join(out)


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def render_html(markdown: str) -> str:
    lines = markdown.splitlines()
    out: list[str] = []
    i = 0
    in_code = False
    code: list[str] = []
    list_tag: str | None = None
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            if in_code:
                if code and code[0].strip().startswith("flowchart"):
                    out.append(architecture_svg())
                else:
                    out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
                code = []
                in_code = False
            else:
                close_list(out, list_tag)
                list_tag = None
                in_code = True
            i += 1
            continue
        if in_code:
            code.append(line)
            i += 1
            continue
        if not line.strip() or line.strip() == "---":
            close_list(out, list_tag)
            list_tag = None
            i += 1
            continue
        if is_table_row(line):
            close_list(out, list_tag)
            list_tag = None
            rows: list[list[str]] = []
            while i < len(lines) and is_table_row(lines[i]):
                cells = table_cells(lines[i])
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                out.append('<div class="table-wrap"><table><thead><tr>' + "".join(f"<th>{inline_html(c)}</th>" for c in rows[0]) + "</tr></thead><tbody>")
                for row in rows[1:]:
                    out.append("<tr>" + "".join(f"<td>{inline_html(c)}</td>" for c in row) + "</tr>")
                out.append("</tbody></table></div>")
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            close_list(out, list_tag)
            list_tag = None
            level = len(heading.group(1))
            out.append(f"<h{level}>{inline_html(heading.group(2))}</h{level}>")
        elif re.match(r"^\s*[-*]\s+", line):
            if list_tag != "ul":
                close_list(out, list_tag)
                out.append("<ul>")
                list_tag = "ul"
            out.append("<li>" + inline_html(re.sub(r"^\s*[-*]\s+", "", line)) + "</li>")
        elif re.match(r"^\s*\d+\.\s+", line):
            if list_tag != "ol":
                close_list(out, list_tag)
                out.append("<ol>")
                list_tag = "ol"
            out.append("<li>" + inline_html(re.sub(r"^\s*\d+\.\s+", "", line)) + "</li>")
        else:
            close_list(out, list_tag)
            list_tag = None
            out.append("<p>" + inline_html(line) + "</p>")
        i += 1
    close_list(out, list_tag)
    body = "\n".join(out)
    css = r"""
@page { size: A4; margin: 18mm 17mm 20mm; @top-left { content: "SemanticSync"; font: 8pt Arial; color: #526174; } @top-right { content: "Research manuscript · October 2026"; font: 8pt Arial; color: #526174; } @bottom-center { content: counter(page); font: 9pt Arial; color: #526174; } }
* { box-sizing: border-box; }
body { font-family: Georgia, "Times New Roman", serif; font-size: 10.25pt; line-height: 1.42; color: #172333; max-width: 178mm; margin: 0 auto; }
h1 { font-size: 22pt; line-height: 1.12; margin: 0 0 12pt; color: #112b45; page-break-after: avoid; }
h2 { font-size: 15pt; line-height: 1.2; margin: 20pt 0 7pt; color: #163d5c; page-break-after: avoid; }
h3 { font-size: 11.5pt; margin: 14pt 0 5pt; color: #1c4d70; page-break-after: avoid; }
p { margin: 0 0 7pt; orphans: 3; widows: 3; }
ul, ol { margin: 3pt 0 9pt 19pt; padding: 0; } li { margin: 0 0 3pt; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; font: 8.2pt/1.25 Arial, sans-serif; margin: 6pt 0 10pt; }
thead { display: table-header-group; } tr { break-inside: avoid; page-break-inside: avoid; }
th { background: #eaf1f6; color: #132f49; font-weight: bold; text-align: left; }
th, td { border: 0.5pt solid #aab9c6; padding: 4pt 4.5pt; vertical-align: top; overflow-wrap: anywhere; }
tbody tr:nth-child(even) { background: #f7f9fb; }
.table-wrap { break-inside: auto; }
code, pre { font-family: "Cascadia Mono", Consolas, monospace; font-size: 8pt; }
code { overflow-wrap: anywhere; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #f4f6f8; border-left: 2pt solid #5a7c98; padding: 7pt; break-inside: avoid; }
a { color: #145d91; text-decoration: underline; }
.math { font-family: "Cambria Math", Georgia, serif; }
.architecture { display: block; width: 100%; height: auto; margin: 5pt 0 9pt; break-inside: avoid; }
.arch-head { font: bold 15px Arial, sans-serif; fill: #163d5c; }
.arch-label { font: 12px Arial, sans-serif; fill: #263746; }
strong { color: #132f49; }
"""
    return "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>SemanticSync Research Manuscript</title><style>" + css + "</style></head><body>" + body + "</body></html>"


def close_list(out: list[str], tag: str | None) -> None:
    if tag:
        out.append(f"</{tag}>")


def render_tex(markdown: str) -> str:
    lines = markdown.splitlines()
    out = [r"\documentclass[runningheads]{llncs}", r"\usepackage[T1]{fontenc}", r"\usepackage{longtable,array,amsmath}", r"\usepackage{hyperref}", r"\setlength{\emergencystretch}{2em}", r"\title{SemanticSync: Schema-Level Semantic Merge Policies for Local-First Relational Databases}", r"\titlerunning{SemanticSync}", r"\author{Pathak Ashmit Akhilesh\inst{1} \and Yash Bohra\inst{1}}", r"\authorrunning{Pathak and Bohra}", r"\institute{VIT Vellore (department and exact institutional style to be confirmed)}", r"\begin{document}", r"\maketitle"]
    i = 1
    in_code = False
    code: list[str] = []
    list_open: str | None = None
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            if in_code:
                out += [r"\begin{quote}\small\ttfamily", r"\obeylines\obeyspaces", *[r"\detokenize{" + l.replace("}", r"\}") + "}" for l in code], r"\end{quote}"]
                in_code, code = False, []
            else:
                if list_open:
                    out.append(r"\end{" + list_open + "}")
                    list_open = None
                in_code = True
            i += 1
            continue
        if in_code:
            code.append(line)
            i += 1
            continue
        if not line.strip() or line.strip() == "---":
            if list_open:
                out.append(r"\end{" + list_open + "}")
                list_open = None
            i += 1
            continue
        if is_table_row(line):
            if list_open:
                out.append(r"\end{" + list_open + "}")
                list_open = None
            rows: list[list[str]] = []
            while i < len(lines) and is_table_row(lines[i]):
                cells = table_cells(lines[i])
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                n = len(rows[0])
                widths = {2: ("0.22\\textwidth", "0.70\\textwidth"), 3: ("0.18\\textwidth", "0.32\\textwidth", "0.34\\textwidth"), 4: ("0.15\\textwidth", "0.15\\textwidth", "0.32\\textwidth", "0.32\\textwidth"), 5: ("0.12\\textwidth", "0.12\\textwidth", "0.23\\textwidth", "0.23\\textwidth", "0.23\\textwidth"), 6: ("0.10\\textwidth", "0.11\\textwidth", "0.18\\textwidth", "0.18\\textwidth", "0.18\\textwidth", "0.13\\textwidth")}.get(n, tuple([f"{0.90/n:.2f}\\textwidth"]*n))
                spec = "".join("p{" + w + "}" for w in widths)
                out.append(r"\begin{longtable}{" + spec + "}")
                out.append(" & ".join(r"\textbf{" + inline_tex(c) + "}" for c in rows[0]) + r" \\\hline")
                out.append(r"\endfirsthead\hline " + " & ".join(r"\textbf{" + inline_tex(c) + "}" for c in rows[0]) + r" \\\hline\endhead")
                for row in rows[1:]:
                    row += [""] * max(0, n-len(row))
                    out.append(" & ".join(inline_tex(c) for c in row[:n]) + r" \\")
                out.append(r"\end{longtable}")
            continue
        if line.strip() == "$$":
            formula: list[str] = []
            i += 1
            while i < len(lines) and lines[i].strip() != "$$":
                formula.append(lines[i])
                i += 1
            out.append(r"\[" + " ".join(formula) + r"\]")
            i += 1
            continue
        if line.strip().startswith("$$") and line.strip().endswith("$$") and len(line.strip()) > 4:
            out.append(r"\[" + line.strip()[2:-2] + r"\]")
            i += 1
            continue
        h = re.match(r"^(#{1,6})\s+(.+)$", line)
        if h:
            if list_open:
                out.append(r"\end{" + list_open + "}")
                list_open = None
            level = len(h.group(1))
            raw_title = re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", h.group(2))
            title = inline_tex(raw_title)
            if level == 1:
                # Title is already provided in the document front matter.
                pass
            elif level == 2 and raw_title.strip() == "References":
                out += [r"\bibliographystyle{splncs04}", r"\bibliography{references}"]
                i = len(lines)
                continue
            elif level == 2:
                out.append(r"\section{" + title + "}")
            elif level == 3:
                out.append(r"\subsection{" + title + "}")
            else:
                out.append(r"\subsubsection{" + title + "}")
        elif line.startswith("**Authors:**") or line.startswith("**Affiliation:**"):
            # Author and affiliation are already rendered by \maketitle.
            pass
        elif line.startswith("**Date:**") or line.startswith("**Artifact Repository:**"):
            out.append(r"\noindent " + inline_tex(line) + r"\par")
        elif line.lstrip().startswith(("- ", "* ")) or re.match(r"^\s*\d+\.\s+", line):
            kind = "enumerate" if re.match(r"^\s*\d+\.\s+", line) else "itemize"
            item = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", line)
            if list_open != kind:
                if list_open:
                    out.append(r"\end{" + list_open + "}")
                out.append(r"\begin{" + kind + "}")
                list_open = kind
            out.append(r"\item " + inline_tex(item))
        else:
            if list_open:
                out.append(r"\end{" + list_open + "}")
                list_open = None
            out.append(inline_tex(line) + "\n")
        i += 1
    if list_open:
        out.append(r"\end{" + list_open + "}")
    out.append(r"\end{document}")
    return "\n".join(out) + "\n"


def pdf_inline(text: str) -> str:
    """Translate the manuscript's small inline-Markdown subset to ReportLab XML."""
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^ )]+)\)", r'<link href="\2" color="#145d91">\1</link>', text)
    def plain_math(match: re.Match[str]) -> str:
        value = match.group(1)
        value = re.sub(r"\\text\{([^{}]*)\}", r"\1", value)
        for token, replacement in ((r"\times", "×"), (r"\cup", "∪"), (r"\to", "→"), (r"\in", "∈"), (r"\bot", "⊥"), (r"\min", "min"), (r"\max", "max")):
            value = value.replace(token, replacement)
        return value.replace(r"\{", "{").replace(r"\}", "}")
    text = re.sub(r"\$([^$]+)\$", plain_math, text)
    text = re.sub(r"\\text\{([^{}]*)\}", r"\1", text)
    return text


def render_pdf(markdown: str) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import reportlab
    from reportlab.platypus import (
        BaseDocTemplate, Frame, LongTable,
        PageTemplate, Paragraph, Spacer, TableStyle,
    )

    page_width, page_height = A4
    left, right, top, bottom = 17 * mm, 17 * mm, 19 * mm, 19 * mm
    usable = page_width - left - right
    navy = colors.HexColor("#163d5c")
    pale = colors.HexColor("#eaf1f6")
    font_sets = [
        (Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts", ("times.ttf", "timesbd.ttf", "timesi.ttf", "arial.ttf", "arialbd.ttf")),
        (Path("/usr/share/fonts/truetype/liberation2"), ("LiberationSerif-Regular.ttf", "LiberationSerif-Bold.ttf", "LiberationSerif-Italic.ttf", "LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf")),
        (Path("/usr/share/fonts/truetype/dejavu"), ("DejaVuSerif.ttf", "DejaVuSerif-Bold.ttf", "DejaVuSerif.ttf", "DejaVuSans.ttf", "DejaVuSans-Bold.ttf")),
        (Path(reportlab.__file__).parent / "fonts", ("Vera.ttf", "VeraBd.ttf", "VeraIt.ttf", "Vera.ttf", "VeraBd.ttf")),
    ]
    font_files = next(((base, files) for base, files in font_sets if all((base / name).is_file() for name in files)), None)
    if font_files is None:
        raise RuntimeError("No supported serif and sans-serif font set was found for the PDF")
    font_dir, font_names = font_files
    pdfmetrics.registerFont(TTFont("PaperSerif", str(font_dir / font_names[0])))
    pdfmetrics.registerFont(TTFont("PaperSerif-Bold", str(font_dir / font_names[1])))
    pdfmetrics.registerFont(TTFont("PaperSerif-Italic", str(font_dir / font_names[2])))
    pdfmetrics.registerFont(TTFont("PaperSans", str(font_dir / font_names[3])))
    pdfmetrics.registerFont(TTFont("PaperSans-Bold", str(font_dir / font_names[4])))
    pdfmetrics.registerFontFamily("PaperSerif", normal="PaperSerif", bold="PaperSerif-Bold", italic="PaperSerif-Italic", boldItalic="PaperSerif-Bold")
    pdfmetrics.registerFontFamily("PaperSans", normal="PaperSans", bold="PaperSans-Bold", italic="PaperSans", boldItalic="PaperSans-Bold")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="PaperTitle", parent=styles["Title"], fontName="PaperSerif-Bold", fontSize=20, leading=23, alignment=TA_LEFT, textColor=colors.HexColor("#112b45"), spaceAfter=13))
    styles.add(ParagraphStyle(name="Author", parent=styles["Normal"], fontName="PaperSerif-Bold", fontSize=11, leading=14, spaceAfter=3))
    styles.add(ParagraphStyle(name="Affiliation", parent=styles["Normal"], fontName="PaperSerif-Italic", fontSize=9.5, leading=12, textColor=colors.HexColor("#526174"), spaceAfter=4))
    styles.add(ParagraphStyle(name="Section1", parent=styles["Heading1"], fontName="PaperSerif-Bold", fontSize=15, leading=18, textColor=navy, spaceBefore=14, spaceAfter=7, keepWithNext=True))
    styles.add(ParagraphStyle(name="Section2", parent=styles["Heading2"], fontName="PaperSerif-Bold", fontSize=11.5, leading=14, textColor=navy, spaceBefore=11, spaceAfter=5, keepWithNext=True))
    styles.add(ParagraphStyle(name="Section3", parent=styles["Heading3"], fontName="PaperSerif-Bold", fontSize=10.3, leading=12.4, textColor=navy, spaceBefore=8, spaceAfter=4, keepWithNext=True))
    styles.add(ParagraphStyle(name="PaperBody", parent=styles["BodyText"], fontName="PaperSerif", fontSize=9.4, leading=13.1, spaceAfter=6, alignment=TA_LEFT, allowWidows=0, allowOrphans=0))
    styles.add(ParagraphStyle(name="Reference", parent=styles["BodyText"], fontName="PaperSerif", fontSize=8.6, leading=10.6, spaceAfter=3.5, leftIndent=12, firstLineIndent=-12, allowWidows=0, allowOrphans=0))
    styles.add(ParagraphStyle(name="TableHead", parent=styles["BodyText"], fontName="PaperSans-Bold", fontSize=8.0, leading=9.6, textColor=colors.HexColor("#132f49"), spaceAfter=0))
    styles.add(ParagraphStyle(name="TableCell", parent=styles["BodyText"], fontName="PaperSans", fontSize=8.0, leading=9.7, spaceAfter=0, wordWrap="CJK"))
    styles.add(ParagraphStyle(name="CodeBlock", parent=styles["Code"], fontName="Courier", fontSize=7.2, leading=9.3, leftIndent=7, rightIndent=5, borderColor=colors.HexColor("#5a7c98"), borderWidth=1, borderPadding=6, backColor=colors.HexColor("#f4f6f8"), spaceBefore=3, spaceAfter=8))

    class ManuscriptDoc(BaseDocTemplate):
        def __init__(self, filename: Path):
            super().__init__(str(filename), pagesize=A4, leftMargin=left, rightMargin=right, topMargin=top, bottomMargin=bottom, title="SemanticSync: Schema-Level Semantic Merge Policies for Local-First Relational Databases", author="Pathak Ashmit Akhilesh; Yash Bohra", subject="Research manuscript")
            frame = Frame(left, bottom, usable, page_height-top-bottom, id="paper", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
            self.addPageTemplates(PageTemplate(id="paper", frames=frame, onPage=self.decorate))

        def decorate(self, canvas, doc):
            canvas.saveState()
            canvas.setStrokeColor(colors.HexColor("#ccd5dd"))
            canvas.setLineWidth(0.45)
            canvas.line(left, page_height-12*mm, page_width-right, page_height-12*mm)
            canvas.setFont("PaperSans", 7.4)
            canvas.setFillColor(colors.HexColor("#526174"))
            canvas.drawString(left, page_height-9.5*mm, "SemanticSync")
            canvas.drawRightString(page_width-right, page_height-9.5*mm, "Research manuscript - October 2026")
            canvas.line(left, 13*mm, page_width-right, 13*mm)
            canvas.drawCentredString(page_width/2, 8.5*mm, str(doc.page))
            canvas.restoreState()

    def make_table(rows: list[list[str]]) -> LongTable:
        count = len(rows[0])
        widths_by_count = {
            2: [0.25, 0.75],
            3: [0.22, 0.31, 0.47],
            4: [0.12, 0.14, 0.38, 0.36],
            5: [0.11, 0.10, 0.28, 0.27, 0.24],
            6: [0.11, 0.11, 0.15, 0.23, 0.23, 0.17],
        }
        fractions = widths_by_count.get(count, [1/count]*count)
        widths = [usable*f for f in fractions]
        data = [[Paragraph(pdf_inline(cell), styles["TableHead"]) for cell in rows[0]]]
        for row in rows[1:]:
            data.append([Paragraph(pdf_inline(cell), styles["TableCell"]) for cell in row])
        table = LongTable(data, colWidths=widths, repeatRows=1, hAlign="LEFT", splitByRow=1)
        commands = [
            ("BACKGROUND", (0, 0), (-1, 0), pale),
            ("TEXTCOLOR", (0, 0), (-1, 0), navy),
            ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#aab9c6")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for row_index in range(2, len(data), 2):
            commands.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#f7f9fb")))
        table.setStyle(TableStyle(commands))
        return table

    def architecture_figure():
        drawing = Drawing(usable, 160)
        columns = [
            (8, 135, "Client replicas", ["Application / client UI", "SQLite driver", "Local SQLite database", "Supported tracked writes"]),
            (169, 145, "SemanticSync engine", ["Schema inspector + validator", "Three-way conflict detector", "Semantic policy resolver", "Foreign-key quarantine", "HLC metadata", "Checkpoint / compaction"]),
            (341, 127, "Sync services", ["Base ancestor store", "Checkpoint manifest store", "FastAPI sync reconciler"]),
        ]
        for x, width, label, entries in columns:
            drawing.add(Rect(x, 3, width, 151, rx=5, ry=5, fillColor=colors.HexColor("#f5f8fa"), strokeColor=colors.HexColor("#9aabba"), strokeWidth=0.8))
            drawing.add(String(x+7, 140, label, fontName="PaperSans-Bold", fontSize=8.2, fillColor=navy))
            row_y = 117
            for entry in entries:
                drawing.add(Rect(x+7, row_y, width-14, 17, rx=2, ry=2, fillColor=colors.white, strokeColor=colors.HexColor("#c6d1da"), strokeWidth=0.55))
                drawing.add(String(x+12, row_y+5.2, entry, fontName="PaperSans", fontSize=6.8, fillColor=colors.HexColor("#263746")))
                row_y -= 20
        drawing.add(Line(143, 78, 166, 78, strokeColor=colors.HexColor("#55758f"), strokeWidth=1.2))
        drawing.add(Polygon([166, 78, 160, 81, 160, 75], fillColor=colors.HexColor("#55758f"), strokeColor=colors.HexColor("#55758f")))
        drawing.add(Line(314, 78, 338, 78, strokeColor=colors.HexColor("#55758f"), strokeWidth=1.2))
        drawing.add(Polygon([338, 78, 332, 81, 332, 75], fillColor=colors.HexColor("#55758f"), strokeColor=colors.HexColor("#55758f")))
        return drawing

    story = []
    lines = markdown.splitlines()
    i = 0
    in_code = False
    code_lines: list[str] = []
    in_references = False
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            if in_code:
                if code_lines and code_lines[0].strip().startswith("flowchart"):
                    story.extend([Spacer(1, 2), architecture_figure(), Spacer(1, 7)])
                else:
                    code = "<br/>".join(html.escape(c, quote=False).replace(" ", "&nbsp;") for c in code_lines)
                    story.append(Paragraph(code, styles["CodeBlock"]))
                code_lines = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_lines.append(line)
            i += 1
            continue
        if not line.strip() or line.strip() == "---":
            i += 1
            continue
        if is_table_row(line):
            rows = []
            while i < len(lines) and is_table_row(lines[i]):
                cells = table_cells(lines[i])
                if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                    rows.append(cells)
                i += 1
            if rows:
                story.extend([Spacer(1, 3), make_table(rows), Spacer(1, 7)])
            continue
        h = re.match(r"^(#{1,6})\s+(.+)$", line)
        if h:
            level, title = len(h.group(1)), h.group(2)
            if title == "References":
                in_references = True
            if level == 1:
                story.append(Paragraph(pdf_inline(title), styles["PaperTitle"]))
            elif level == 2:
                story.append(Paragraph(pdf_inline(title), styles["Section1"]))
            elif level == 3:
                story.append(Paragraph(pdf_inline(title), styles["Section2"]))
            else:
                story.append(Paragraph(pdf_inline(title), styles["Section3"]))
            i += 1
            continue
        if line.startswith("**Authors:**"):
            story.append(Paragraph(pdf_inline(line.replace("**Authors:**", "Authors:")), styles["Author"]))
        elif line.startswith("**Affiliation:**"):
            story.append(Paragraph(pdf_inline(line.replace("**Affiliation:**", "Affiliation:")), styles["Affiliation"]))
        elif line.startswith("**Date:**"):
            story.append(Paragraph(pdf_inline(line.replace("**Date:**", "Date:")), styles["Affiliation"]))
        elif line.startswith("**Artifact Repository:**"):
            story.append(Paragraph(pdf_inline(line.replace("**Artifact Repository:**", "Artifact repository:")), styles["Affiliation"]))
        elif line.lstrip().startswith(("- ", "* ")):
            item = re.sub(r"^\s*[-*]\s+", "", line)
            story.append(Paragraph("- &nbsp;" + pdf_inline(item), styles["PaperBody"]))
        elif re.match(r"^\s*\d+\.\s+", line):
            number = int(re.match(r"^\s*(\d+)\.", line).group(1))
            item = re.sub(r"^\s*\d+\.\s+", "", line)
            style = styles["Reference"] if in_references else styles["PaperBody"]
            story.append(Paragraph(f"{number}.&nbsp; " + pdf_inline(item), style))
        elif line.strip().startswith("$$") and line.strip().endswith("$$"):
            formula = line.strip()[2:-2].replace(r"\text{", "").replace("}", "")
            story.append(Paragraph(pdf_inline(formula), styles["PaperBody"]))
        else:
            story.append(Paragraph(pdf_inline(line), styles["PaperBody"]))
        i += 1
    PDF_OUT.parent.mkdir(parents=True, exist_ok=True)
    ManuscriptDoc(PDF_OUT).build(story)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", action="store_true", help="generate a print-ready PDF with ReportLab")
    args = parser.parse_args()
    source = SOURCE.read_text(encoding="utf-8")
    HTML_OUT.write_text(render_html(source), encoding="utf-8", newline="\n")
    TEX_OUT.parent.mkdir(parents=True, exist_ok=True)
    TEX_OUT.write_text(render_tex(source), encoding="utf-8", newline="\n")
    print(f"Wrote {HTML_OUT.relative_to(ROOT)} and {TEX_OUT.relative_to(ROOT)} from {SOURCE.relative_to(ROOT)}")
    if args.pdf:
        render_pdf(source)
        print(f"Printed {PDF_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
