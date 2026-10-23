import pathlib
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parents[2]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from research.build_manuscript import architecture_svg

svg_str = architecture_svg()
html_content = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{
    margin: 0;
    padding: 10px;
    background: #ffffff;
    display: inline-block;
}}
svg {{
    display: block;
}}
</style>
</head>
<body>
{svg_str}
</body>
</html>"""

audit_dir = root / "research" / "paper_audit_20261020"
html_path = audit_dir / "fig1_arch.html"
png_path = audit_dir / "fig1_architecture.png"

html_path.write_text(html_content, encoding="utf-8")

edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
cmd = [
    edge_path,
    "--headless",
    "--disable-gpu",
    f"--screenshot={png_path.resolve()}",
    "--window-size=920,440",
    "--default-background-color=0xffffffff",
    str(html_path.resolve())
]
subprocess.run(cmd, check=True)
print(f"Generated Fig 1 PNG: {png_path} ({png_path.stat().st_size} bytes)")
