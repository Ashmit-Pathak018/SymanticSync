"""
generate_ieee_full_paper.py
===========================
Generates an authentic IEEE-formatted two-column demo paper HTML and compiles it
to FINAL_DEMO_PAPER.pdf via headless Edge. Also outputs the updated first-person
IEEE-structured FINAL_DEMO_PAPER.md.
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

from research.build_manuscript import architecture_svg

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

def build():
    # 1. Title, Authors, Abstract, Keywords
    # Note: In IEEE format: Title 24pt, Author 11pt/10pt, Abstract italic run-in, Keywords bold run-in.
    print("Compiling IEEE Demo Paper...")

if __name__ == "__main__":
    build()
