import shutil
from pathlib import Path

src_dir = Path(r"C:\Users\ASMIT\Downloads\DBMS-REVIEWPAPERS")
papers_dir = Path("papers")
exp_papers_dir = Path("explanation/papers")

papers_dir.mkdir(parents=True, exist_ok=True)
exp_papers_dir.mkdir(parents=True, exist_ok=True)

copied = []
for f in src_dir.glob("*.pdf"):
    shutil.copy2(f, papers_dir / f.name)
    shutil.copy2(f, exp_papers_dir / f.name)
    copied.append(f.name)

print(f"Successfully copied {len(copied)} PDF papers to both {papers_dir.resolve()} and {exp_papers_dir.resolve()}!")
