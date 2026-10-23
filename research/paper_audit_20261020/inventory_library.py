import pathlib
import pypdf
import re
import json

src_dir = pathlib.Path(r'C:\Users\ASMIT\Downloads\DBMS-REVIEWPAPERS')
pdfs = sorted(list(src_dir.rglob('*.pdf')))

inventory = []

for idx, p in enumerate(pdfs, 1):
    try:
        reader = pypdf.PdfReader(str(p))
        num_pages = len(reader.pages)
        meta = reader.metadata or {}
        
        # Extract text from first 2 pages
        text_p1 = reader.pages[0].extract_text() or ''
        text_p2 = reader.pages[1].extract_text() if num_pages > 1 else ''
        full_intro = text_p1 + '\n' + text_p2
        
        # Clean lines
        lines = [l.strip() for l in text_p1.splitlines() if l.strip()]
        
        # Find DOI
        doi_m = re.search(r'10\.\d{4,9}/[-._;()/:A-Za-z0-9]+', full_intro)
        doi = doi_m.group(0).rstrip(').,;') if doi_m else ''
        
        # Extract abstract
        abs_text = ''
        abs_m = re.search(r'(?:Abstract|ABSTRACT)[\s—\-\.](.*?)(?:Introduction|INTRODUCTION|1\.|\n\n\n)', full_intro, re.DOTALL)
        if abs_m:
            abs_text = ' '.join(abs_m.group(1).split())[:400]
        
        item = {
            'index': idx,
            'filename': p.name,
            'pages': num_pages,
            'meta_title': meta.title or '',
            'meta_author': meta.author or '',
            'doi': doi,
            'first_lines': lines[:8],
            'abstract_snippet': abs_text,
        }
        inventory.append(item)
    except Exception as e:
        inventory.append({
            'index': idx,
            'filename': p.name,
            'error': str(e)
        })

out_json = pathlib.Path('research/paper_audit_20261020/library_inventory.json')
out_json.write_text(json.dumps(inventory, indent=2), encoding='utf-8')
print(f'Processed {len(inventory)} PDFs successfully!')
