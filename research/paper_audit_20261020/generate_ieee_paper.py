"""
generate_ieee_paper.py
======================
Generates an authentic IEEE-format two-column demo paper HTML and PDF.

Key features:
- Authentic IEEE Conference format:
  * A4 paper size, 2-column layout (after Title/Author/Abstract spanning block)
  * Times New Roman body text (10pt, justified, hyphenation, 12pt line height)
  * Title: 24pt bold, centered
  * Authors: 2-column author block with affiliations (VIT Vellore)
  * Abstract: bold heading run-in, italic text, single-block spanning
  * Headings: IEEE Roman numerals (I. INTRODUCTION, II. SYSTEM ARCHITECTURE, etc.)
  * Subheadings: Italic uppercase letters (A. The Local-First Relational Dilemma, etc.)
  * First-person narrative voice throughout ("I", "we", "our")
  * Tables: IEEE style with caption above ("TABLE I", "TABLE II", etc.)
  * Figures: IEEE style with caption below ("Fig. 1. ...")
  * Equations centered with flush-right numbering: (1), (2)
  * References: standard IEEE bracketed numbers [1], [2]
"""
import os
import re
import html
import subprocess
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
AUDIT_DIR = ROOT / "research" / "paper_audit_20261020"
OUT_MD = AUDIT_DIR / "FINAL_DEMO_PAPER.md"
OUT_HTML = AUDIT_DIR / "FINAL_DEMO_PAPER_IEEE.html"
OUT_PDF = AUDIT_DIR / "FINAL_DEMO_PAPER.pdf"

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

from research.build_manuscript import architecture_svg

# IEEE CSS styling
IEEE_CSS = """
@page {
    size: A4 portrait;
    margin: 19mm 14mm 22mm 14mm;
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
    line-height: 1.25;
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
    font-size: 24pt;
    font-weight: bold;
    line-height: 1.15;
    margin: 0 0 12pt 0;
    text-transform: capitalize;
}

.author-block {
    display: flex;
    justify-content: center;
    gap: 40pt;
    margin-bottom: 14pt;
    font-size: 10pt;
    line-height: 1.2;
}

.author-col {
    text-align: center;
    max-width: 220pt;
}

.author-name {
    font-size: 11pt;
    font-weight: bold;
    margin-bottom: 2pt;
}

.author-dept, .author-inst, .author-city, .author-email {
    font-size: 10pt;
    color: #222;
}

.abstract-keywords-block {
    width: 100%;
    margin-bottom: 14pt;
    padding: 0 18pt;
    text-align: justify;
    text-justify: inter-word;
}

.abstract-text {
    font-size: 9pt;
    line-height: 1.2;
    font-weight: bold;
    margin-bottom: 6pt;
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
    column-gap: 18pt;
    text-align: justify;
    text-justify: inter-word;
}

/* Headings */
h2.ieee-h1 {
    font-size: 10pt;
    font-weight: normal;
    text-align: center;
    text-transform: uppercase;
    margin: 12pt 0 4pt 0;
    break-after: avoid;
    break-inside: avoid;
}

h3.ieee-h2 {
    font-size: 10pt;
    font-style: italic;
    font-weight: normal;
    margin: 8pt 0 3pt 0;
    text-align: left;
    break-after: avoid;
    break-inside: avoid;
}

h4.ieee-h3 {
    font-size: 10pt;
    font-style: italic;
    font-weight: normal;
    margin: 6pt 0 2pt 0;
    break-after: avoid;
    break-inside: avoid;
}

p {
    font-size: 10pt;
    line-height: 1.25;
    margin: 0 0 5pt 0;
    text-indent: 14pt;
}

p.no-indent {
    text-indent: 0;
}

/* Bullet lists */
ul, ol {
    margin: 2pt 0 6pt 16pt;
    padding: 0;
}

li {
    font-size: 9.5pt;
    line-height: 1.22;
    margin-bottom: 2.5pt;
}

/* Code */
code {
    font-family: 'Courier New', Courier, monospace;
    font-size: 8.5pt;
}

pre {
    font-family: 'Courier New', Courier, monospace;
    font-size: 8pt;
    background: #f8f8f8;
    border: 0.5pt solid #ccc;
    padding: 4pt;
    white-space: pre-wrap;
    word-break: break-all;
    margin: 4pt 0 6pt 0;
    break-inside: avoid;
}

/* Spanning elements (Tables and Figures that span across columns) */
.span-columns {
    column-span: all;
    margin: 10pt 0 12pt 0;
    break-inside: avoid;
}

.column-element {
    width: 100%;
    margin: 8pt 0 10pt 0;
    break-inside: avoid;
}

/* Table styling */
.ieee-table-wrap {
    text-align: center;
    margin-bottom: 10pt;
    break-inside: avoid;
}

.table-title {
    font-size: 8pt;
    text-transform: uppercase;
    text-align: center;
    font-weight: bold;
    margin-bottom: 2pt;
}

.table-caption {
    font-size: 8pt;
    font-style: italic;
    text-align: center;
    margin-bottom: 4pt;
}

table.ieee-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 7.8pt;
    line-height: 1.15;
    margin: 0 auto;
    border-top: 1pt solid #000;
    border-bottom: 1pt solid #000;
}

table.ieee-table th {
    border-top: 1pt solid #000;
    border-bottom: 0.5pt solid #000;
    padding: 3pt 3pt;
    font-weight: bold;
    text-align: center;
    vertical-align: bottom;
}

table.ieee-table td {
    border-top: 0.25pt solid #ddd;
    padding: 2.5pt 3pt;
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
    font-size: 7.5pt;
    line-height: 1.2;
    text-align: justify;
    margin-top: 3pt;
}

/* Figure styling */
.ieee-fig-wrap {
    text-align: center;
    margin: 8pt 0 10pt 0;
    break-inside: avoid;
}

.fig-caption {
    font-size: 8.5pt;
    line-height: 1.2;
    text-align: justify;
    margin-top: 4pt;
}

.fig-caption strong {
    font-weight: bold;
}

/* Equations */
.equation-wrap {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin: 5pt 0 6pt 0;
    padding: 0 4pt;
    font-size: 9.5pt;
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
    font-size: 8pt;
    line-height: 1.2;
    margin-bottom: 3pt;
    text-indent: -18pt;
    margin-left: 18pt;
    text-align: justify;
}

a {
    color: #000;
    text-decoration: underline;
}
"""

def generate():
    print("Generating IEEE paper...")

if __name__ == "__main__":
    generate()
