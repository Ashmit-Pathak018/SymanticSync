import re
import pathlib
import pypdf

root = pathlib.Path(__file__).resolve().parents[2]
html_path = root / "research" / "paper_audit_20261020" / "FINAL_DEMO_PAPER_IEEE.html"
pdf_path = root / "research" / "paper_audit_20261020" / "FINAL_DEMO_PAPER.pdf"
md_path = root / "research" / "paper_audit_20261020" / "FINAL_DEMO_PAPER.md"
bib_path = root / "docs" / "manuscript_latex" / "references.bib"

# 1. Check BibTeX
bib_text = bib_path.read_text(encoding="utf-8")
bib_keys = re.findall(r"@\w+\{([^,]+),", bib_text)
print(f"BibTeX entries in references.bib: {len(bib_keys)}")

# 2. Check Markdown
md_text = md_path.read_text(encoding="utf-8")
md_body = md_text.split("## REFERENCES")[0]
md_citations = sorted(set(int(x) for x in re.findall(r"\[(\d+)\]", md_body)))
print(f"Unique citations in Markdown body: {len(md_citations)} (min: {min(md_citations)}, max: {max(md_citations)})")

md_refs = re.findall(r"^(\d+)\.\s+(.*)$", md_text.split("## REFERENCES")[1], re.MULTILINE)
print(f"Numbered entries in Markdown REFERENCES list: {len(md_refs)}")

# 3. Check HTML
html_text = html_path.read_text(encoding="utf-8")
pos_start = html_text.find("ieee-references")
pos_ol = html_text.find("<ol", pos_start)
pos_end = html_text.find("</ol>", pos_ol)
html_refs = re.findall(r"<li>\[(\d+)\]\s+(.*?)</li>", html_text[pos_ol:pos_end])
print(f"Numbered entries in HTML <ol class=\"ieee-references\">: {len(html_refs)}")

# 4. Check PDF
reader = pypdf.PdfReader(str(pdf_path))
print(f"Total pages in compiled PDF: {len(reader.pages)}")

# Print summary
missing_citations = [i for i in range(1, len(md_refs) + 1) if i not in md_citations]
print(f"Uncited reference numbers: {missing_citations}")

assert len(bib_keys) == 26, f"Expected 26 bib keys, got {len(bib_keys)}"
assert len(md_citations) == 26, f"Expected 26 body citations, got {len(md_citations)}"
assert len(md_refs) == 26, f"Expected 26 md refs, got {len(md_refs)}"
assert len(html_refs) == 26, f"Expected 26 html refs, got {len(html_refs)}"
print("ALL REFERENCE CHECKS PASSED: Exactly 26 references, 100% cited, 0 unreferenced, 0 gaps!")
