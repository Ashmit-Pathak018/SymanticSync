# SemanticSync — Faculty Defense & Technical Explanation Package

**Project:** SemanticSync: Schema-Level Semantic Merge Policies for Local-First Relational Databases  
**Authors:** Pathak Ashmit Akhilesh and Yash Bohra  
**Institution:** Department of Computer Science and Engineering, Vellore Institute of Technology, Vellore  
**Target Venue:** IEEE / Academic Faculty Examination Committee  
**Date:** October 2026  

---

## Welcome Reviewers & Examiners

This directory (`explanation/`) aggregates all core technical explanation, presentation scripts, research literature audits, and architectural proofs created for the defense of **SemanticSync**.

### Directory Manifest

| File | Type | Target Read Time | Description & Purpose |
| :--- | :--- | :---: | :--- |
| [`PRESENTATION_CHEATSHEET.md`](PRESENTATION_CHEATSHEET.md) | Markdown | 2 mins | **1-Page Quick Reference Sheet:** 30s elevator pitch, 5 core contributions, 1-minute architecture, SET vs INCREMENT worked example, 10 faculty Q&As, and essential commands. |
| [`DEMO_GUIDE.md`](DEMO_GUIDE.md) | Markdown | 5 mins | **Live Demonstration Guide:** Step-by-step 8–12 minute script for faculty presentation, pre-demo checklist, 3 live demonstrations (Additive Increment vs LWW, Safety Halting via `REJECT`, Foreign-Key Quarantine under active `PRAGMA foreign_keys = ON`), and zero-downtime recovery fallbacks. |
| [`TECHNICAL_EXPLANATION.md`](TECHNICAL_EXPLANATION.md) | Markdown | 15 mins | **Comprehensive Technical Compendium:** 20-section architectural deep dive, system architecture diagram, end-to-end data flow, formal algebra of 8 merge policies, 4-case HLC derivation, referential integrity quarantine protocol, compaction horizon ($H_{\text{stable}}$), metadata schemas, and **26 substantive faculty defense Q&As**. |
| [`CLAIM_EVIDENCE_AUDIT.md`](CLAIM_EVIDENCE_AUDIT.md) | Markdown | 10 mins | **Claim-to-Evidence Traceability Matrix:** Rigorous line-by-line verification auditing all 24 scientific claims in the manuscript against exact code implementations in `backend/` and `frontend/`. |
| [../papers/](../papers/) | Directory (25 PDFs) | — | **Raw Research Papers Directory:** Contains the complete collection of 25 raw PDF research papers referenced across the project. |
| [`RESEARCH_LITERATURE_INDEX.md`](RESEARCH_LITERATURE_INDEX.md) | Markdown | 10 mins | **Research Literature Library Index:** Complete bibliographic index of all 25 research papers stored in the primary research library (`C:\Users\ASMIT\Downloads\DBMS-REVIEWPAPERS`), detailing citations, DOIs, licensing status, and technical mapping to SemanticSync components. |
| [`IEEE_DEMO_PAPER.pdf`](IEEE_DEMO_PAPER.pdf) | PDF (Binary) | 12 mins | **Compiled IEEE Research Manuscript:** The official 6-page IEEE format paper, typeset in LaTeX with zero overfull hboxes, cropped vector architecture diagram, humanized academic prose, and verified bibliography. |

---

## Quick-Start Demo Execution

To demonstrate SemanticSync live in under 2 minutes:

### 1. Start the Backend (Isolated Test Workspace)
```powershell
$env:SEMANTICSYNC_DATA_DIR = Join-Path $env:TEMP ("SemanticSync-Demo-" + [guid]::NewGuid().ToString("N"))
py -3.14 main.py --no-reload
```

### 2. Start the Studio Frontend
```powershell
cd frontend
npm run dev
```
Open **`http://localhost:5173`** in your browser.

### 3. Verify System Health
```powershell
curl.exe -s http://127.0.0.1:8000/api/v1/health
```

---

## Authors & Contact

- **Pathak Ashmit Akhilesh** (`pathak.ashmit2025@vitstudent.ac.in`)
- **Yash Bohra** (`yash.bohra2025@vitstudent.ac.in`)

*Department of Computer Science and Engineering, Vellore Institute of Technology, Vellore, Tamil Nadu, India.*
