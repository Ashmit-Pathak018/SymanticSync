import pathlib
import pypdf
import re
import json

src_dir = pathlib.Path(r'C:\Users\ASMIT\Downloads\DBMS-REVIEWPAPERS')
pdfs = sorted(list(src_dir.rglob('*.pdf')))

records = []

for idx, p in enumerate(pdfs, 1):
    reader = pypdf.PdfReader(str(p))
    n_pages = len(reader.pages)
    text_p1 = reader.pages[0].extract_text() if n_pages > 0 else ''
    text_p2 = reader.pages[1].extract_text() if n_pages > 1 else ''
    full_first = text_p1 + '\n' + text_p2

    lines = [l.strip() for l in text_p1.splitlines() if l.strip()]

    # Extract DOI
    doi_m = re.search(r'10\.\d{4,9}/[-._;()/:A-Za-z0-9]+', full_first)
    doi = doi_m.group(0).rstrip(').,;') if doi_m else ''

    records.append({
        'index': idx,
        'filename': p.name,
        'pages': n_pages,
        'lines': lines[:12],
        'doi': doi,
        'meta_title': reader.metadata.title if reader.metadata else '',
        'meta_author': reader.metadata.author if reader.metadata else '',
    })

for r in records:
    print(f"=== [{r['index']:02d}] {r['filename']} ({r['pages']} pp) ===")
    print(f"DOI: {r['doi']}")
    print(f"MetaTitle: {r['meta_title']}")
    print("Lines:")
    for l in r['lines'][:6]:
        print("   ", l.encode('ascii', errors='replace').decode('ascii'))
    print()
