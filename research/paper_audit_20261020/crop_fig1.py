import subprocess
from pathlib import Path
import pypdf

# 1. Read existing SVG from fig1_arch.html
fig1_arch_path = Path("research/paper_audit_20261020/fig1_arch.html")
orig_content = fig1_arch_path.read_text(encoding="utf-8")
svg_start = orig_content.find("<svg")
svg_end = orig_content.find("</svg>") + 6
svg_code = orig_content[svg_start:svg_end]

# 2. Create HTML with exact page size CSS
# viewBox is 0 0 900 228 (aspect ratio 900:228 = 3.947:1)
# In points: 900pt by 230pt (or inches: 7.5in by 1.916in)
custom_html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
@page {{
    size: 900pt 232pt;
    margin: 0;
}}
html, body {{
    margin: 0;
    padding: 0;
    background: #ffffff;
    width: 900pt;
    height: 232pt;
    overflow: hidden;
}}
svg {{
    display: block;
    width: 900pt;
    height: 228pt;
}}
.arch-head {{ font: bold 14px Arial, sans-serif; fill: #163d5c; }}
.arch-label {{ font: 12px Arial, sans-serif; fill: #263746; }}
</style>
</head>
<body>
{svg_code}
</body>
</html>
"""

custom_html_path = Path("research/paper_audit_20261020/fig1_arch_custom.html")
custom_html_path.write_text(custom_html, encoding="utf-8")

# 3. Print to PDF via Edge
edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
out_pdf = Path("research/paper_audit_20261020/fig1_architecture_cropped.pdf")

cmd = [
    edge_path,
    "--headless=new",
    "--disable-gpu",
    "--no-pdf-header-footer",
    f"--print-to-pdf={out_pdf.resolve()}",
    custom_html_path.resolve().as_uri()
]

print("Running Edge print-to-pdf...")
res = subprocess.run(cmd, capture_output=True, text=True)
print("Return code:", res.returncode)

if out_pdf.exists():
    reader = pypdf.PdfReader(str(out_pdf))
    page = reader.pages[0]
    print(f"Generated PDF successfully!")
    print(f"Page mediabox: {page.mediabox.left}, {page.mediabox.bottom}, {page.mediabox.right}, {page.mediabox.top}")
    print(f"Page count: {len(reader.pages)}")
else:
    print("PDF was not created.")
