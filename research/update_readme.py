from pathlib import Path

p = Path("README.md")
content = p.read_text(encoding="utf-8")

header_target = "# SemanticSync 🔄\n\n> **A developer workspace for designing, querying, and synchronizing local-first relational databases with schema-level semantic merge policies.**\n\n---"
if header_target not in content:
    header_target = "# SemanticSync 🔄\r\n\r\n> **A developer workspace for designing, querying, and synchronizing local-first relational databases with schema-level semantic merge policies.**\r\n\r\n---"

new_section = """# SemanticSync 🔄

> **A developer workspace for designing, querying, and synchronizing local-first relational databases with schema-level semantic merge policies.**

**Authors:** Pathak Ashmit Akhilesh & Yash Bohra  
**Institution:** Department of Computer Science and Engineering, Vellore Institute of Technology, Vellore  
**Target Venue:** IEEE / Academic Faculty Defense  

---

## 📚 Faculty Defense & Technical Documentation Quick-Access

For reviewing and demonstrating SemanticSync during faculty presentation and technical defense:

| Document | Purpose | Location |
| :--- | :--- | :--- |
| **Presentation Cheatsheet** | 1-page quick reference (pitch, 5 contributions, 10 faculty Q&As, commands) | [`docs/PRESENTATION_CHEATSHEET.md`](docs/PRESENTATION_CHEATSHEET.md) |
| **Live Demonstration Guide** | 8–12 minute minute-by-minute script, pre-demo checklist, 3 live demos, fallbacks | [`docs/DEMO_GUIDE.md`](docs/DEMO_GUIDE.md) |
| **Technical Explanation** | 20-section deep dive (architecture, data flow, 8 policies, HLC, FK quarantine, 26 Q&As) | [`docs/TECHNICAL_EXPLANATION.md`](docs/TECHNICAL_EXPLANATION.md) |
| **Claim-to-Evidence Audit** | Traceability matrix proving all 24 scientific claims against the codebase | [`docs/CLAIM_EVIDENCE_AUDIT.md`](docs/CLAIM_EVIDENCE_AUDIT.md) |
| **Research Literature Index** | Index of all 25 reference papers with licensing and technical connections | [`papers/README.md`](papers/README.md) |
| **Compiled IEEE Paper (PDF)** | Fully compiled 6-page IEEE format research manuscript with 0 overfull hboxes | [`docs/manuscript_latex/IEEE_DEMO_PAPER.pdf`](docs/manuscript_latex/IEEE_DEMO_PAPER.pdf) |
| **IEEE Paper Source (LaTeX)** | LaTeX source file for the IEEE demo paper | [`docs/manuscript_latex/IEEE_DEMO_PAPER.tex`](docs/manuscript_latex/IEEE_DEMO_PAPER.tex) |

---"""

if header_target in content:
    content = content.replace(header_target, new_section, 1)
    p.write_text(content, encoding="utf-8")
    print("README.md updated successfully with quick-access documentation table!")
else:
    print("Header target not found directly, checking lines...")
    lines = content.splitlines(keepends=True)
    # Replace lines 0 to 5
    rest = "".join(lines[5:])
    new_full = new_section + "\n" + rest
    p.write_text(new_full, encoding="utf-8")
    print("README.md rewritten successfully!")
