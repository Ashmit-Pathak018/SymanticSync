# SemanticSync Research Literature Library Index

**Project:** SemanticSync — Schema-Level Semantic Merge Policies for Local-First Relational Databases  
**Authors:** Pathak Ashmit Akhilesh and Yash Bohra  
**Institution:** Department of Computer Science and Engineering, Vellore Institute of Technology, Vellore  
**Primary Research Source Directory:** `C:\Users\ASMIT\Downloads\DBMS-REVIEWPAPERS`

---

## 1. Overview and Copyright Policy

This directory catalogues the academic literature, formal papers, and foundational research referenced throughout the design, implementation, and evaluation of **SemanticSync**.

> [!IMPORTANT]
> **Redistribution Policy:** To respect academic copyright and publisher licensing restrictions (IEEE, ACM, Springer, Elsevier, etc.), commercial third-party publisher PDFs stored in the local working library (`DBMS-REVIEWPAPERS`) are **not** committed to the public Git repository. Instead, this index provides complete bibliographic metadata, official DOI links, Open Access / arXiv preprints where available, and detailed notes on how each work informs SemanticSync.

Our own research manuscript and camera-ready demo paper are provided in full in `docs/manuscript_latex/`:
- **Manuscript LaTeX Source:** [`docs/manuscript_latex/IEEE_DEMO_PAPER.tex`](../docs/manuscript_latex/IEEE_DEMO_PAPER.tex)
- **Compiled Manuscript PDF:** [`docs/manuscript_latex/IEEE_DEMO_PAPER.pdf`](../docs/manuscript_latex/IEEE_DEMO_PAPER.pdf)
- **Audited Evaluation Markdown:** [`research/paper_audit_20261020/FINAL_DEMO_PAPER.md`](../research/paper_audit_20261020/FINAL_DEMO_PAPER.md)

---

## 2. Annotated Literature Library

### [1] `synql2024` — Synql.pdf
- **Citation:** C.-L. Ignat, V. Elvinger, and H. Ba, 'Synql: A CRDT-Based Approach for Replicated Relational Databases with Integrity Constraints', in Proc. DAIS 2024, LNCS 14677, pp. 18-35, 2024. DOI: 10.1007/978-3-031-62638-8_2
- **License / Distribution Status:** Springer Nature Copyright (Subscription via DOI)
- **Relevant Sections:** Section 3-4, pp. 22-28
- **Core Contribution:** Composes CRDT primitives (LWW-element-set, multi-value registers) to replicate relational tables and enforces foreign key/unique integrity constraints by generating compensatory delete/update actions.
- **Role in SemanticSync:** Relational CRDT replication with integrity constraint handling; contrasts with SemanticSync schema-level policy assignment and non-destructive quarantine.

### [2] `crdv2025` — Conflict-free Replicated Data Views (2025).pdf
- **Citation:** N. Faria and J. Pereira, 'CRDV: Conflict-free Replicated Data Views', Proc. ACM Manag. Data, vol. 3, no. 1, Art. 25, pp. 1-27, 2025. DOI: 10.1145/3709675
- **License / Distribution Status:** ACM Copyright (Subscription / Open Access via DOI)
- **Relevant Sections:** Section 1-3, pp. 2-8
- **Core Contribution:** Proposes conflict-free replicated data views over SQL databases to specify domain-specific merge semantics declaratively through SQL views without altering base engine tables.
- **Role in SemanticSync:** Declarative relational merge semantics; supports SemanticSync goal of schema-assigned merge logic without whole-database virtual table replacements.

### [3] `thomassen2023` — Eventually-Consistent Replicated Relations and Updatable Views (2023).pdf
- **Citation:** J. Thomassen and W. Yu, 'Eventually-Consistent Replicated Relations and Updatable Views', in New Trends in Database and Information Systems, CCIS 1850, pp. 187-196, 2023. DOI: 10.1007/978-3-031-42941-5_17
- **License / Distribution Status:** Springer Nature Copyright (Subscription via DOI)
- **Relevant Sections:** Section 2-4, pp. 189-194
- **Core Contribution:** Formalizes conflict-free replicated relations (CRR) and updatable views to resolve relational conflicts under eventual consistency.
- **Role in SemanticSync:** Relational view updates under eventual consistency; supports literature comparison on relational CRDT models.

### [4] `tomter2021` — 978-3-030-85082-1.pdf
- **Citation:** I. T. Tomter and W. Yu, 'Augmenting SQLite for Local-First Software', in Proc. ADBIS 2021 Short Papers, CCIS 1450, pp. 233-243, 2021. DOI: 10.1007/978-3-030-85082-1_22
- **License / Distribution Status:** Springer Nature Copyright (Subscription via DOI)
- **Relevant Sections:** Section 1-3, pp. 234-239
- **Core Contribution:** Augments standard SQLite with Conflict-free Replicated Relations (CRR) using auxiliary delta tables and SQL triggers without modifying SQLite internals.
- **Role in SemanticSync:** Directly supports SemanticSync design of implementing local-first replication over unmodified SQLite engines using change-log triggers/middleware.

### [5] `riffle2023` — Riffle (2023).pdf
- **Citation:** G. Litt, N. Schiefer, J. Schickling, and D. Jackson, 'Riffle: Reactive Relational State for Local-First Applications', in Proc. UIST 2023, Art. 102, pp. 1-16, 2023. DOI: 10.1145/3586183.3606801
- **License / Distribution Status:** Third-Party Copyright / Academic Subscription
- **Relevant Sections:** Section 3-5, pp. 4-9
- **Core Contribution:** Combines client-side relational storage (SQLite via WASM) with reactive queries for local-first UI applications.
- **Role in SemanticSync:** Client-side relational state management in local-first apps; illustrates adjacent local-first architecture without schema-level conflict resolution.

### [6] `schiefer2022` — Merge What You Can, Fork What You Can't (2022).pdf
- **Citation:** N. Schiefer, G. Litt, and D. Jackson, 'Merge What You Can, Fork What You Can't: Managing Data Integrity in Local-First Software', in Proc. PaPoC 2022, pp. 24-32, 2022. DOI: 10.1145/3517209.3524041
- **License / Distribution Status:** Third-Party Copyright / Academic Subscription
- **Relevant Sections:** Section 2-4, pp. 25-29
- **Core Contribution:** Introduces history forking when automatic merge would violate application data integrity invariants that cannot be resolved automatically.
- **Role in SemanticSync:** Data integrity in local-first software; contrasts with SemanticSync foreign-key quarantine and REJECT policy flagging instead of branch forking.

### [7] `conloc2025` — Consistent_Local-First_Software_Enforcing_Safety_and_Invariants_for_Local-First_Applications.pdf
- **Citation:** M. Köhler, G. Zakhour, P. Weisenburger, and G. Salvaneschi, 'Consistent Local-First Software: Enforcing Safety and Invariants for Local-First Applications', IEEE Trans. Softw. Eng., vol. 51, no. 1, pp. 53-65, 2025. DOI: 10.1109/TSE.2024.3477723
- **License / Distribution Status:** IEEE Copyright (Subscription / Open Access via DOI)
- **Relevant Sections:** Section III-V, pp. 55-61
- **Core Contribution:** Develops ConLoc, a system enforcing safety invariants in local-first software using mixed-consistency transactions and invariant analysis.
- **Role in SemanticSync:** Invariant preservation in local-first software; provides formal contrast to SemanticSync BOUNDED_SUM and quarantine invariants.

### [8] `lore2024` — LoRe.pdf
- **Citation:** J. Haas, R. Mogk, E. Yanakieva, A. Bieniusa, and M. Mezini, 'LoRe: A Programming Model for Verifiably Safe Local-first Software', ACM Trans. Program. Lang. Syst., vol. 46, no. 1, Art. 2, pp. 1-26, 2024. DOI: 10.1145/3633769
- **License / Distribution Status:** ACM Copyright (Subscription / Open Access via DOI)
- **Relevant Sections:** Section 2-4, pp. 4-15
- **Core Contribution:** Presents a verified programming model using state-based invariant contracts to guarantee safety for local-first applications.
- **Role in SemanticSync:** Verified safety for local-first applications; supports discussion on limitations of unverified heuristic merge policies.

### [9] `borrego2025` — Ensuring Convergence and Invariants Without Coordination.pdf
- **Citation:** D. Borrego, N. Preguiça, E. Gonzalez Boix, and C. Ferreira, 'Ensuring Convergence and Invariants Without Coordination', in Proc. ECOOP 2025, LIPIcs 333, Art. 4, pp. 4:1-4:29, 2025. DOI: 10.4230/LIPIcs.ECOOP.2025.4
- **License / Distribution Status:** Open Access (CC-BY / LIPIcs)
- **Relevant Sections:** Section 3-5, pp. 6-18
- **Core Contribution:** Formalizes a framework to preserve integrity invariants across concurrent operations without coordination using semantic operation restrictions.
- **Role in SemanticSync:** Coordination-free invariant preservation; provides theoretical context for SemanticSync BOUNDED_SUM and relational integrity bounds.

### [10] `antidotesql2018` — Antidote SQL SQL for Weakly Consistent Databases.pdf
- **Citation:** P. M. S. Lopes, 'Antidote SQL: SQL for Weakly Consistent Databases', Master's thesis, NOVA University Lisbon, 2018.
- **License / Distribution Status:** Open Academic Repository (University Thesis)
- **Relevant Sections:** Chapter 3-4, pp. 29-55
- **Core Contribution:** Extends AntidoteDB with a SQL interface translating relational queries and foreign key constraints into CRDT operations.
- **Role in SemanticSync:** SQL interfaces over weakly consistent stores; contrasts distributed cloud CRDT backend with local-first embedded SQLite.

### [11] `bauwens2023` — LIPIcs.ECOOP.2023.2.pdf
- **Citation:** J. Bauwens and E. Gonzalez Boix, 'Nested Pure Operation-Based CRDTs', in Proc. ECOOP 2023, LIPIcs 263, Art. 2, pp. 2:1-2:26, 2023. DOI: 10.4230/LIPIcs.ECOOP.2023.2
- **License / Distribution Status:** Open Access (CC-BY / LIPIcs)
- **Relevant Sections:** Section 3-4, pp. 5-14
- **Core Contribution:** Formalizes pure operation-based CRDTs that transmit compact operation messages without causal metadata bloat, managing operation history and causal delivery.
- **Role in SemanticSync:** Operation-based replication models; directly supports SemanticSync explicit-INCREMENT operation logging and receipt tracking versus state-based diffing.

### [12] `crust2025` — Crust_A_Modular_Framework_for_Conflict-Free_Replicated_Data_Types_CRDTs_Development_Validation_and_Benchmarking.pdf
- **Citation:** Y. Zhu and J. Ma, 'Crust: A Modular Framework for Conflict-Free Replicated Data Types (CRDTs) Development, Validation, and Benchmarking', IEEE Access, vol. 13, pp. 83870-83882, 2025. DOI: 10.1109/ACCESS.2025.3568925
- **License / Distribution Status:** IEEE Copyright (Subscription / Open Access via DOI)
- **Relevant Sections:** Section III-V, pp. 83872-83878
- **Core Contribution:** Proposes a modular evaluation and benchmarking framework for CRDT implementations, stressing the need for reproducible conflict generation and semantic validation.
- **Role in SemanticSync:** Benchmarking and validation methodology for replicated data types; supports SemanticSync empirical audit harness design and reproducible seed-matrix methodology.

### [13] `removewin2021` — Remove-Win_a_Design_Framework_for_Conflict-free_Replicated_Data_Types.pdf
- **Citation:** Y. Zhang, H. Wei, and Y. Huang, 'Remove-Win: a Design Framework for Conflict-free Replicated Data Types', in Proc. ICPADS 2021, pp. 597-604, 2021. DOI: 10.1109/ICPADS53394.2021.00081
- **License / Distribution Status:** Third-Party Copyright / Academic Subscription
- **Relevant Sections:** Section III-IV, pp. 599-602
- **Core Contribution:** Investigates concurrent update vs delete conflicts in CRDT sets and maps, formalizing remove-wins semantics to prevent resurrection of deleted entities.
- **Role in SemanticSync:** Tombstone and deletion semantics; directly supports SemanticSync UPDATE_DELETE conflict handling (DELETE_WINS vs UPDATE_RESURRECTS).

### [14] `stewen2024` — 3642976.3653029.pdf
- **Citation:** L. Stewen and M. Kleppmann, 'Undo and Redo Support for Replicated Registers', in Proc. PaPoC 2024, pp. 1-7, 2024. DOI: 10.1145/3642976.3653029
- **License / Distribution Status:** Third-Party Copyright / Academic Subscription
- **Relevant Sections:** Section 2-4, pp. 2-5
- **Core Contribution:** Formalizes collaborative undo/redo semantics for replicated registers (LWW and multi-value), showing how non-linear operation histories affect value reversion.
- **Role in SemanticSync:** Replicated register semantics and operation history tracking; relevant to undo and operation logging in local-first data stores.

### [15] `barreto2023` — 1-s2.0-S0167739X22004186-main.pdf
- **Citation:** A. Barreto, H. Paulino, J. A. Silva, and N. Preguiça, 'PS-CRDTs: CRDTs in highly volatile environments', Future Generation Computer Systems, vol. 141, pp. 755-767, 2023. DOI: 10.1016/j.fgcs.2022.12.016
- **License / Distribution Status:** Third-Party Copyright / Academic Subscription
- **Relevant Sections:** Section 3-5, pp. 757-762
- **Core Contribution:** Addresses state-based and operation-based CRDT synchronization over publish/subscribe in volatile mobile edge environments with intermittent connectivity.
- **Role in SemanticSync:** Mobile edge replication under intermittent disconnection; relevant background for local-first network synchronization assumptions.

### [16] `schiebelbein2024` — 3642976.3653036.pdf
- **Citation:** E. Schiebelbein, S. Hatia, A. Bieniusa, G. Petri, C. Ferreira, and M. Shapiro, 'Models for Storage in Database Backends: A Rigorous Approach for Formally-Correct Designs', in Proc. PaPoC 2024, pp. 1-9, 2024. DOI: 10.1145/3642976.3653036
- **License / Distribution Status:** Third-Party Copyright / Academic Subscription
- **Relevant Sections:** Section 2-4, pp. 2-6
- **Core Contribution:** Formalizes transactional storage layers and durability boundaries for database backends supporting replicated data.
- **Role in SemanticSync:** Database backend storage models; relevant background for SQLite storage layer and transaction boundaries.

### [17] `power2024` — 3642976.3653031.pdf
- **Citation:** C. Power, S. Achalla, R. Cottone, N. Macasaet, and J. M. Hellerstein, 'Wrapping Rings in Lattices: An Algebraic Symbiosis of Incremental View Maintenance and Eventual Consistency', in Proc. PaPoC 2024, pp. 1-8, 2024. DOI: 10.1145/3642976.3653031
- **License / Distribution Status:** Third-Party Copyright / Academic Subscription
- **Relevant Sections:** Section 2-4, pp. 2-5
- **Core Contribution:** Combines semilattices (CRDTs) with groups/rings (incremental view maintenance) to enable delta-based algebraic view maintenance with eventual consistency.
- **Role in SemanticSync:** Algebraic delta merges and incremental computation; provides mathematical context for delta-based additive merges.

### [18] `deporre2023` — LIPIcs.ECOOP.2023.9.pdf
- **Citation:** K. De Porre, C. Ferreira, and E. Gonzalez Boix, 'VeriFx: Correct Replicated Data Types for the Masses', in Proc. ECOOP 2023, LIPIcs 263, Art. 9, pp. 9:1-9:45, 2023. DOI: 10.4230/LIPIcs.ECOOP.2023.9
- **License / Distribution Status:** Open Access (CC-BY / LIPIcs)
- **Relevant Sections:** Section 3-6, pp. 7-25
- **Core Contribution:** Presents VeriFx, a programming language and automated verification tool proving convergence and invariant preservation for replicated data types using SMT solvers.
- **Role in SemanticSync:** Automated verification of convergence and invariants; provides context for why empirical validation is necessary in SemanticSync when formal verification is absent.

### [19] `nieto2022` — 3563351.pdf
- **Citation:** A. Nieto, L. Gondelman, A. Reynaud, A. Timany, and L. Birkedal, 'Modular Verification of Op-Based CRDTs in Separation Logic', Proc. ACM Program. Lang., vol. 6, no. OOPSLA2, Art. 188, pp. 1-29, 2022. DOI: 10.1145/3563351
- **License / Distribution Status:** ACM Copyright (Subscription / Open Access via DOI)
- **Relevant Sections:** Section 2-5, pp. 4-18
- **Core Contribution:** Uses Iris separation logic to verify causal delivery and convergence of operation-based CRDTs in concurrent settings.
- **Role in SemanticSync:** Formal verification of operation-based replication; theoretical context for operation commutativity and causal delivery.

### [20] `nieto2023` — LIPIcs.ECOOP.2023.22.pdf
- **Citation:** A. Nieto, A. Daby-Seesaram, L. Gondelman, A. Timany, and L. Birkedal, 'Modular Verification of State-Based CRDTs in Separation Logic', in Proc. ECOOP 2023, LIPIcs 263, Art. 22, pp. 22:1-22:27, 2023. DOI: 10.4230/LIPIcs.ECOOP.2023.22
- **License / Distribution Status:** Open Access (CC-BY / LIPIcs)
- **Relevant Sections:** Section 2-5, pp. 4-16
- **Core Contribution:** Verifies state-based CRDT lattice joins and convergence in separation logic.
- **Role in SemanticSync:** Formal verification of state-based CRDTs.

### [21] `yanakieva2021` — 3447865.3457970.pdf
- **Citation:** E. Yanakieva, M. Youssef, A. H. Rezae, and A. Bieniusa, 'Access Control Conflict Resolution in Distributed File Systems using CRDTs', in Proc. PaPoC 2021, pp. 1-3, 2021. DOI: 10.1145/3447865.3457970
- **License / Distribution Status:** IEEE Copyright (Subscription / Open Access via DOI)
- **Relevant Sections:** Section 1-3, pp. 1-3
- **Core Contribution:** Applies CRDT conflict resolution to access control list (ACL) conflicts in distributed file systems.
- **Role in SemanticSync:** Access control conflict resolution; adjacent to security policies.

### [22] `da2024` — 3642976.3653030.pdf
- **Citation:** L. Da and M. Kleppmann, 'Extending JSON CRDTs with Move Operations', in Proc. PaPoC 2024, pp. 1-7, 2024. DOI: 10.1145/3642976.3653030
- **License / Distribution Status:** Third-Party Copyright / Academic Subscription
- **Relevant Sections:** Section 2-4, pp. 2-5
- **Core Contribution:** Extends JSON tree CRDTs to support subtree move operations without creating cycles.
- **Role in SemanticSync:** Tree moves in JSON documents.

### [23] `freudenthaler2024` — 3650212.3685555.pdf
- **Citation:** L. Freudenthaler, 'Decentralized Near-Synchronous Local-First Programming Collaboration', in Companion Proc. ACM SIGPLAN OOPSLA 2024, pp. 1-3, 2024. DOI: 10.1145/3650212.3685555
- **License / Distribution Status:** ACM Copyright (Subscription / Open Access via DOI)
- **Relevant Sections:** Section 1-2, pp. 1-3
- **Core Contribution:** Doctoral symposium abstract on near-synchronous collaborative code editing environments using CRDTs.
- **Role in SemanticSync:** Collaborative programming editor prototype.

### [24] `kuessner2023` — LIPIcs.ECOOP.2023.14.pdf
- **Citation:** C. Kuessner, R. Mogk, A.-K. Wickert, and M. Mezini, 'Algebraic Replicated Data Types: Programming Secure Local-First Software', in Proc. ECOOP 2023, LIPIcs 263, Art. 14, pp. 14:1-14:33, 2023. DOI: 10.4230/LIPIcs.ECOOP.2023.14
- **License / Distribution Status:** Open Access (CC-BY / LIPIcs)
- **Relevant Sections:** Section 2-5, pp. 4-18
- **Core Contribution:** Presents Algebraic Replicated Data Types for secure decentralized multi-user local-first applications with cryptographic access control.
- **Role in SemanticSync:** Security and access control in local-first apps.

### [25] `esop2020` — 978-3-030-44914-8.pdf
- **Citation:** P. Müller (Ed.), 'Programming Languages and Systems: 29th European Symposium on Programming (ESOP 2020)', LNCS 12075, Springer, 2020. DOI: 10.1007/978-3-030-44914-8
- **License / Distribution Status:** Springer Nature Copyright (Subscription via DOI)
- **Relevant Sections:** Entire volume (785 pp)
- **Core Contribution:** Complete conference proceedings volume containing 28 separate papers on programming languages and formal methods.
- **Role in SemanticSync:** Entire proceedings volume; not an individual research paper.
