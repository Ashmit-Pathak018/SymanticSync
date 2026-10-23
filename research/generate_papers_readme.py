import csv
from pathlib import Path

csv_path = Path('research/paper_audit_20261020/SOURCE_TO_CLAIM_MATRIX.csv')
papers_dir = Path('papers')
papers_dir.mkdir(exist_ok=True)

with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

lines = []
lines.append('# SemanticSync Research Literature Library Index\n')
lines.append('**Project:** SemanticSync — Schema-Level Semantic Merge Policies for Local-First Relational Databases  ')
lines.append('**Authors:** Pathak Ashmit Akhilesh and Yash Bohra  ')
lines.append('**Institution:** Department of Computer Science and Engineering, Vellore Institute of Technology, Vellore  ')
lines.append('**Primary Research Source Directory:** `C:\\Users\\ASMIT\\Downloads\\DBMS-REVIEWPAPERS`\n')
lines.append('---\n')
lines.append('## 1. Overview and Copyright Policy\n')
lines.append('This directory catalogues the academic literature, formal papers, and foundational research referenced throughout the design, implementation, and evaluation of **SemanticSync**.\n')
lines.append('> [!IMPORTANT]')
lines.append('> **Redistribution Policy:** To respect academic copyright and publisher licensing restrictions (IEEE, ACM, Springer, Elsevier, etc.), commercial third-party publisher PDFs stored in the local working library (`DBMS-REVIEWPAPERS`) are **not** committed to the public Git repository. Instead, this index provides complete bibliographic metadata, official DOI links, Open Access / arXiv preprints where available, and detailed notes on how each work informs SemanticSync.\n')
lines.append('Our own research manuscript and camera-ready demo paper are provided in full in `docs/manuscript_latex/`:')
lines.append('- **Manuscript LaTeX Source:** [`docs/manuscript_latex/IEEE_DEMO_PAPER.tex`](../docs/manuscript_latex/IEEE_DEMO_PAPER.tex)')
lines.append('- **Compiled Manuscript PDF:** [`docs/manuscript_latex/IEEE_DEMO_PAPER.pdf`](../docs/manuscript_latex/IEEE_DEMO_PAPER.pdf)')
lines.append('- **Audited Evaluation Markdown:** [`research/paper_audit_20261020/FINAL_DEMO_PAPER.md`](../research/paper_audit_20261020/FINAL_DEMO_PAPER.md)')
lines.append('\n---\n')
lines.append('## 2. Annotated Literature Library\n')

for i, r in enumerate(rows, 1):
    fn = r.get('source_filename', '')
    ck = r.get('citation_key', '')
    meta = r.get('verified_metadata', '')
    sec = r.get('relevant_section_or_page', '')
    finding = r.get('technical_finding_or_contribution', '')
    claim = r.get('manuscript_claim_supported', '')
    
    # Classify rights
    if 'arxiv' in meta.lower():
        lic = 'Open Access (arXiv Preprint)'
    elif 'lipics' in meta.lower():
        lic = 'Open Access (CC-BY / LIPIcs)'
    elif 'thesis' in meta.lower():
        lic = 'Open Academic Repository (University Thesis)'
    elif 'ieee' in meta.lower() or 'access' in meta.lower():
        lic = 'IEEE Copyright (Subscription / Open Access via DOI)'
    elif 'acm' in meta.lower():
        lic = 'ACM Copyright (Subscription / Open Access via DOI)'
    elif 'springer' in meta.lower() or 'lncs' in meta.lower() or 'ccis' in meta.lower():
        lic = 'Springer Nature Copyright (Subscription via DOI)'
    else:
        lic = 'Third-Party Copyright / Academic Subscription'
        
    lines.append(f'### [{i}] `{ck}` — {fn}')
    lines.append(f'- **Citation:** {meta}')
    lines.append(f'- **License / Distribution Status:** {lic}')
    lines.append(f'- **Relevant Sections:** {sec}')
    lines.append(f'- **Core Contribution:** {finding}')
    lines.append(f'- **Role in SemanticSync:** {claim}')
    lines.append('')

output_file = Path('papers/README.md')
output_file.write_text('\n'.join(lines), encoding='utf-8')
print(f'Successfully generated {output_file} ({len(lines)} lines)!')
