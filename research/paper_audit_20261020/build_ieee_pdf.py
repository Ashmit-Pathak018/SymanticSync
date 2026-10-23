"""
build_ieee_pdf.py
=================
Builds an authentic IEEE two-column demo paper HTML and PDF from
FINAL_DEMO_PAPER.md.
"""
import os
import re
import html
import subprocess
import pathlib

import sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

AUDIT_DIR = ROOT / "research" / "paper_audit_20261020"
SRC_MD = AUDIT_DIR / "FINAL_DEMO_PAPER.md"
OUT_HTML = AUDIT_DIR / "FINAL_DEMO_PAPER_IEEE.html"
OUT_PDF = AUDIT_DIR / "FINAL_DEMO_PAPER.pdf"

from research.build_manuscript import architecture_svg

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

IEEE_CSS = """
@page {
    size: A4 portrait;
    margin: 18mm 14mm 20mm 14mm;
    @bottom-center {
        content: counter(page);
        font-family: 'Times New Roman', Times, serif;
        font-size: 10pt;
    }
}

* {
    box-sizing: border-box;
}

body {
    font-family: 'Times New Roman', Times, serif;
    font-size: 10pt;
    line-height: 1.22;
    color: #000;
    margin: 0;
    padding: 0;
    background: #fff;
}

/* Header spanning both columns */
.ieee-header {
    width: 100%;
    text-align: center;
    margin-bottom: 12pt;
}

.paper-title {
    font-size: 22pt;
    font-weight: bold;
    line-height: 1.15;
    margin: 0 0 10pt 0;
}

.author-block {
    display: flex;
    justify-content: center;
    gap: 40pt;
    margin-bottom: 12pt;
    font-size: 9.5pt;
    line-height: 1.2;
}

.author-col {
    text-align: center;
    max-width: 220pt;
}

.author-name {
    font-size: 10.5pt;
    font-weight: bold;
    margin-bottom: 2pt;
}

.author-dept, .author-inst, .author-city, .author-email {
    font-size: 9.5pt;
    color: #222;
}

.abstract-keywords-block {
    width: 100%;
    margin-bottom: 12pt;
    padding: 0 14pt;
    text-align: justify;
    text-justify: inter-word;
}

.abstract-text {
    font-size: 9pt;
    line-height: 1.2;
    font-weight: bold;
    margin-bottom: 5pt;
}

.abstract-heading {
    font-style: italic;
    font-weight: bold;
}

.keywords-text {
    font-size: 9pt;
    line-height: 1.2;
}

.keywords-heading {
    font-style: italic;
    font-weight: bold;
}

/* Two-column layout for body */
.two-column-layout {
    column-count: 2;
    column-gap: 16pt;
    text-align: justify;
    text-justify: inter-word;
}

/* Headings */
h2.ieee-h1 {
    font-size: 10pt;
    font-weight: bold;
    text-align: center;
    text-transform: uppercase;
    margin: 10pt 0 3pt 0;
    break-after: avoid;
    break-inside: avoid;
}

h3.ieee-h2 {
    font-size: 10pt;
    font-style: italic;
    font-weight: bold;
    margin: 7pt 0 2pt 0;
    text-align: left;
    break-after: avoid;
    break-inside: avoid;
}

p {
    font-size: 9.5pt;
    line-height: 1.22;
    margin: 0 0 4.5pt 0;
    text-indent: 12pt;
}

p.no-indent {
    text-indent: 0;
}

/* Bullet lists */
ul, ol {
    margin: 2pt 0 5pt 14pt;
    padding: 0;
}

li {
    font-size: 9pt;
    line-height: 1.2;
    margin-bottom: 2pt;
}

/* Code */
code {
    font-family: 'Courier New', Courier, monospace;
    font-size: 8.2pt;
}

pre {
    font-family: 'Courier New', Courier, monospace;
    font-size: 7.8pt;
    background: #f8f8f8;
    border: 0.5pt solid #ccc;
    padding: 3.5pt;
    white-space: pre-wrap;
    word-break: break-all;
    margin: 3pt 0 5pt 0;
    break-inside: avoid;
}

/* Spanning elements (Tables and Figures that span across columns) */
.span-columns {
    column-span: all;
    margin: 8pt 0 10pt 0;
    break-inside: avoid;
}

.column-element {
    width: 100%;
    margin: 6pt 0 8pt 0;
    break-inside: avoid;
}

/* Table styling */
.ieee-table-wrap {
    text-align: center;
    margin-bottom: 8pt;
    break-inside: avoid;
}

.table-title {
    font-size: 7.8pt;
    text-transform: uppercase;
    text-align: center;
    font-weight: bold;
    margin-bottom: 1.5pt;
}

.table-caption {
    font-size: 7.8pt;
    font-style: italic;
    text-align: center;
    margin-bottom: 3pt;
}

table.ieee-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 7.5pt;
    line-height: 1.15;
    margin: 0 auto;
    border-top: 0.8pt solid #000;
    border-bottom: 0.8pt solid #000;
}

table.ieee-table th {
    border-top: 0.8pt solid #000;
    border-bottom: 0.5pt solid #000;
    padding: 2.5pt 2.5pt;
    font-weight: bold;
    text-align: center;
    vertical-align: bottom;
}

table.ieee-table td {
    border-top: 0.25pt solid #ddd;
    padding: 2.2pt 2.5pt;
    vertical-align: top;
    text-align: left;
}

table.ieee-table td.center {
    text-align: center;
}

table.ieee-table td.right {
    text-align: right;
}

table.ieee-table tbody tr:first-child td {
    border-top: 0.5pt solid #000;
}

.table-notes {
    font-size: 7.2pt;
    line-height: 1.18;
    text-align: justify;
    margin-top: 2.5pt;
}

/* Figure styling */
.ieee-fig-wrap {
    text-align: center;
    margin: 6pt 0 8pt 0;
    break-inside: avoid;
}

.fig-caption {
    font-size: 8pt;
    line-height: 1.18;
    text-align: justify;
    margin-top: 3pt;
}

.fig-caption strong {
    font-weight: bold;
}

/* Equations */
.equation-wrap {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin: 4pt 0 5pt 0;
    padding: 0 4pt;
    font-size: 9pt;
    break-inside: avoid;
}

.equation-math {
    flex-grow: 1;
    text-align: center;
    font-family: 'Cambria Math', 'Times New Roman', serif;
    font-style: italic;
}

.equation-number {
    font-family: 'Times New Roman', Times, serif;
    font-style: normal;
    text-align: right;
}

/* References */
ol.ieee-references {
    list-style-type: none;
    margin: 0;
    padding: 0;
}

ol.ieee-references li {
    font-size: 7.8pt;
    line-height: 1.16;
    margin-bottom: 2.5pt;
    text-indent: -16pt;
    margin-left: 16pt;
    text-align: justify;
}

a {
    color: #000;
    text-decoration: underline;
}

.math {
    font-family: 'Cambria Math', 'Times New Roman', serif;
    font-style: italic;
}
"""

def parse_inline(text: str) -> str:
    # Protect inline math $...$ from HTML escaping and markdown regex
    math_spans = []
    def save_math(m):
        math_spans.append(m.group(0))
        return f"@@MATH_{len(math_spans)-1}@@"
    
    text = re.sub(r"(?<!\\)\$[^$]+\$", save_math, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^ )]+)\)", r'<a href="\2">\1</a>', text)
    
    # Restore math spans
    for idx, span in enumerate(math_spans):
        text = text.replace(f"@@MATH_{idx}@@", span)
    return text

def parse_markdown_to_ieee_html(md_text: str) -> str:
    # 1. Parse Title, Authors, Abstract, Keywords
    title_m = re.search(r"^#\s+(.+)$", md_text, re.M)
    title = title_m.group(1).strip() if title_m else "SemanticSync"

    # Extract Abstract
    abs_m = re.search(r"### Abstract\s*\n(.*?)(?=\n\n\*\*Keywords\*\*|\n\*\*Keywords\*\*)", md_text, re.DOTALL)
    abs_text = abs_m.group(1).strip() if abs_m else ""

    # Extract Keywords
    kw_m = re.search(r"\*\*Keywords\*\*—([^\n]+)", md_text)
    keywords = kw_m.group(1).strip() if kw_m else ""

    header_html = f"""
    <div class="ieee-header">
        <h1 class="paper-title">{html.escape(title)}</h1>
        <div class="author-block">
            <div class="author-col">
                <div class="author-name">Pathak Ashmit Akhilesh</div>
                <div class="author-dept">Dept. of Computer Science and Engineering</div>
                <div class="author-inst">Vellore Institute of Technology</div>
                <div class="author-city">Vellore, India</div>
                <div class="author-email">pathak.ashmit2025@vitstudent.ac.in</div>
            </div>
            <div class="author-col">
                <div class="author-name">Yash Bohra</div>
                <div class="author-dept">Dept. of Computer Science and Engineering</div>
                <div class="author-inst">Vellore Institute of Technology</div>
                <div class="author-city">Vellore, India</div>
                <div class="author-email">yash.bohra2025@vitstudent.ac.in</div>
            </div>
        </div>
        <div class="abstract-keywords-block">
            <div class="abstract-text"><span class="abstract-heading">Abstract</span>—{parse_inline(abs_text)}</div>
            <div class="keywords-text"><span class="keywords-heading">Keywords</span>—{parse_inline(keywords)}</div>
        </div>
    </div>
    """

    # 2. Parse Body sections
    body_md = md_text[kw_m.end():] if kw_m else md_text
    # Remove leading horizontal rules
    body_md = re.sub(r"^\s*---\s*", "", body_md.strip())

    lines = body_md.splitlines()
    body_out = ['<div class="two-column-layout">']

    i = 0
    in_code = False
    code_lines = []
    in_list = False
    in_references = False
    ref_items = []

    while i < len(lines):
        line = lines[i]

        # References section
        if line.strip().startswith("## REFERENCES"):
            if in_list:
                body_out.append("</ul>")
                in_list = False
            in_references = True
            body_out.append('<h2 class="ieee-h1">References</h2>')
            body_out.append('<ol class="ieee-references">')
            i += 1
            continue

        if in_references:
            ref_m = re.match(r"^(\d+)\.\s+(.*)$", line.strip())
            if ref_m:
                ref_num = ref_m.group(1)
                ref_text = ref_m.group(2)
                body_out.append(f"<li>[{ref_num}] {parse_inline(ref_text)}</li>")
            i += 1
            continue

        # Code block
        if line.startswith("```"):
            if in_code:
                # End of code
                if code_lines and code_lines[0].strip().startswith("flowchart"):
                    # Insert SVG spanning both columns
                    svg_html = architecture_svg()
                    caption = "<strong>Fig. 1.</strong> SemanticSync architectural layers, illustrating the flow of tracked replica mutations through the schema inspector, conflict detector, semantic resolver, and quarantine manager."
                    body_out.append(f'<div class="span-columns"><div class="ieee-fig-wrap">{svg_html}<div class="fig-caption">{caption}</div></div></div>')
                else:
                    code_content = html.escape("\n".join(code_lines))
                    body_out.append(f"<pre><code>{code_content}</code></pre>")
                code_lines = []
                in_code = False
            else:
                if in_list:
                    body_out.append("</ul>")
                    in_list = False
                in_code = True
            i += 1
            continue

        if in_code:
            code_lines.append(line)
            i += 1
            continue

        # Blank or hr
        if not line.strip() or line.strip() == "---":
            if in_list:
                body_out.append("</ul>")
                in_list = False
            i += 1
            continue

        # Figure 1 markdown caption skip (since we attached it to the SVG)
        if line.strip().startswith("**Fig. 1.**"):
            i += 1
            continue

        # Tables
        if line.strip().startswith("**TABLE "):
            if in_list:
                body_out.append("</ul>")
                in_list = False
            table_title_match = re.match(r"^\*\*TABLE ([I|V|X]+)\.\*\*\s+(.+)$", line.strip())
            t_num = table_title_match.group(1) if table_title_match else "I"
            t_cap = table_title_match.group(2) if table_title_match else ""
            i += 1
            # Next line might be blank
            while i < len(lines) and not lines[i].strip():
                i += 1
            # Gather table markdown lines
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            # Optional table notes
            notes_lines = []
            while i < len(lines) and lines[i].strip().startswith(("*", "1.", "2.", "3.", "4.", "Analysis", "Notes")):
                notes_lines.append(lines[i].strip())
                i += 1

            # Render IEEE table
            # Parse table cells
            rows = []
            for tl in table_lines:
                cells = [c.strip() for c in tl.strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)

            # Build HTML table
            is_wide_table = len(rows[0]) >= 5
            wrap_class = "span-columns" if is_wide_table else "column-element"
            table_html = [f'<div class="{wrap_class}"><div class="ieee-table-wrap">']
            table_html.append(f'<div class="table-title">TABLE {t_num}</div>')
            table_html.append(f'<div class="table-caption">{html.escape(t_cap)}</div>')
            table_html.append('<table class="ieee-table"><thead><tr>')
            for hcell in rows[0]:
                table_html.append(f'<th>{parse_inline(hcell)}</th>')
            table_html.append('</tr></thead><tbody>')
            for r in rows[1:]:
                table_html.append('<tr>')
                for c_idx, cell in enumerate(r):
                    align_class = "right" if re.search(r"^\+?[\d,\.]+\s*(?:ms|%|s)?$", cell) else ("center" if cell in ("PASS", "FAIL") else "")
                    table_html.append(f'<td class="{align_class}">{parse_inline(cell)}</td>')
                table_html.append('</tr>')
            table_html.append('</tbody></table>')
            if notes_lines:
                table_html.append('<div class="table-notes">')
                for nl in notes_lines:
                    table_html.append(f'<p class="no-indent" style="font-size:7.2pt;margin-bottom:1.5pt;">{parse_inline(nl)}</p>')
                table_html.append('</div>')
            table_html.append('</div></div>')
            body_out.append("\n".join(table_html))
            continue

        # Major Headings (## II. SYSTEM ARCHITECTURE)
        h1_match = re.match(r"^##\s+([I|V|X]+)\.\s+(.+)$", line.strip())
        if h1_match:
            if in_list:
                body_out.append("</ul>")
                in_list = False
            num = h1_match.group(1)
            htitle = h1_match.group(2)
            body_out.append(f'<h2 class="ieee-h1">{num}. {html.escape(htitle)}</h2>')
            i += 1
            continue

        # Subheadings (### A. The Local-First Relational Dilemma)
        h2_match = re.match(r"^###\s+([A-Z])\.\s+(.+)$", line.strip())
        if h2_match:
            if in_list:
                body_out.append("</ul>")
                in_list = False
            num = h2_match.group(1)
            htitle = h2_match.group(2)
            body_out.append(f'<h3 class="ieee-h2"><em>{num}. {html.escape(htitle)}</em></h3>')
            i += 1
            continue

        # Display math $$ ... $$
        if line.strip().startswith("$$") and line.strip().endswith("$$") and len(line.strip()) > 4:
            if in_list:
                body_out.append("</ul>")
                in_list = False
            eq_math = line.strip()[2:-2].strip()
            # Check for equation number e.g. \quad (1)
            eq_num = ""
            num_m = re.search(r"\\quad\s*\(([0-9]+)\)$", eq_math)
            if num_m:
                eq_num = f"({num_m.group(1)})"
                eq_math = eq_math[:num_m.start()].strip()
            # Render equation wrap with KaTeX display delimiter $$
            body_out.append(f'<div class="equation-wrap"><div class="equation-math">$${eq_math}$$</div><div class="equation-number">{eq_num}</div></div>')
            i += 1
            continue

        # Lists
        if re.match(r"^\s*[-*]\s+", line):
            if not in_list:
                body_out.append("<ul>")
                in_list = True
            item_text = re.sub(r"^\s*[-*]\s+", "", line)
            body_out.append(f"<li>{parse_inline(item_text)}</li>")
            i += 1
            continue
        elif re.match(r"^\s*\d+\.\s+", line):
            if not in_list:
                body_out.append("<ol>")
                in_list = True
            item_text = re.sub(r"^\s*\d+\.\s+", "", line)
            body_out.append(f"<li>{parse_inline(item_text)}</li>")
            i += 1
            continue
        else:
            if in_list:
                body_out.append("</ul>")
                in_list = False

        # Regular paragraph
        body_out.append(f"<p>{parse_inline(line.strip())}</p>")
        i += 1

    if in_list:
        body_out.append("</ul>")
    if in_references:
        body_out.append("</ol>")

    body_out.append("</div>") # close two-column-layout

    doc_html = f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{html.escape(title)}</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>
    <script>
    window.addEventListener("DOMContentLoaded", () => {{
        renderMathInElement(document.body, {{
            delimiters: [
                {{left: "$$", right: "$$", display: true}},
                {{left: "$", right: "$", display: false}}
            ],
            throwOnError: false
        }});
    }});
    </script>
    <style>{IEEE_CSS}</style>
</head>
<body>
    {header_html}
    {"".join(body_out)}
</body>
</html>
"""
    return doc_html

def main():
    print(f"Reading source markdown from {SRC_MD}...")
    md_content = SRC_MD.read_text(encoding="utf-8")
    
    print("Generating IEEE HTML document...")
    html_output = parse_markdown_to_ieee_html(md_content)
    OUT_HTML.write_text(html_output, encoding="utf-8")
    print(f"Saved IEEE HTML to {OUT_HTML} ({len(html_output)} bytes)")

    print("Compiling IEEE PDF with Microsoft Edge headless...")
    cmd = [
        EDGE_PATH,
        "--headless",
        "--disable-gpu",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=5000",
        f"--print-to-pdf={OUT_PDF.resolve()}",
        "--no-pdf-header-footer",
        str(OUT_HTML.resolve())
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    print("PDF Returncode:", res.returncode)
    if OUT_PDF.exists():
        print(f"SUCCESS: Generated {OUT_PDF} ({OUT_PDF.stat().st_size} bytes)")
    else:
        print("ERROR: PDF was not generated.")

if __name__ == "__main__":
    main()
