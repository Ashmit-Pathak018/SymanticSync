# SemanticSync — Literature Review & Theoretical Context

**Version:** 2.1 (Evidence-qualified)  
**Field:** Distributed Computing (`cs.DC`), Database Systems (`cs.DB`)

**Scope note:** This is a selective review, not a systematic search. The feature matrix in the prior draft made categorical claims about CR-SQLite, ElectricSQL, and generic LWW systems that were not supported by citations; it is replaced below.

---

## 1. Verified Foundational Literature

### Conflict-Free Replicated Data Types (CRDTs)
- **Shapiro et al. (2011)** — *Conflict-free replicated data types* (SSS 2011).
  - *Contribution:* Formulated State-based (CvRDT) and Operation-based (CmRDT) systems. Proved that monotonic join-semilattices $\langle S, \sqcup \rangle$ guarantee Strong Eventual Consistency (SEC) across partial orders.
  - *Connection to SemanticSync:* Standard LWW registers are join-semilattices over $(\text{timestamp}, \text{value})$ tuples. However, when applied to relational attributes (such as counters or texts), the LWW semilattice ordering ignores operation deltas.
- **Gomes, Kleppmann, et al. (2017)** — *Verifying Strong Eventual Consistency in Distributed Systems* (OOPSLA 2017 / [arXiv:1707.01747](https://arxiv.org/abs/1707.01747)).
  - *Contribution:* Machine-checked verification of CRDT convergence (RGA, OR-Set, PN-Counter) in Isabelle/HOL. Established an axiomatic network model capturing message delivery anomalies.
  - *Relevance to SemanticSync:* Informs our verification strategy. For SemanticSync policies to guarantee SEC, each operator must be rigorously analyzed for commutativity and associativity over historical operations.

### Causality and Hybrid Logical Clocks
- **Kulkarni et al. (2014)** — *Logical Physical Clocks* (OPODIS 2014, LNCS 8878, pp. 17–32, [DOI 10.1007/978-3-319-14472-6_2](https://doi.org/10.1007/978-3-319-14472-6_2)). An earlier University at Buffalo CSE technical report (2014-04) uses the expanded title *Logical Physical Clocks and Consistent Snapshots in Globally Distributed Databases*; the report metadata spells coauthor Deepak Madappa as “Madeppa.”
  - *Contribution:* Introduced hybrid logical clocks and discussed their use in consistent snapshots and distributed databases.
  - *Application:* SemanticSync stores HLC fields and uses supplied timestamps in selected comparisons. It does not establish a network-wide happened-before relation or use HLC alone as proof of checkpoint stability.

### Local-First Relational Systems & Extensions
- **Kleppmann et al. (2019)** — *Local-first software: you own your data, in spite of the cloud* (Onward! 2019).
  - *Contribution:* Defined the seven architectural ideals of local-first software.
- **Edwards, Petricek, and van der Storm (2023)** — *Live & Local Schema Change: Challenge Problems* ([arXiv:2309.11406](https://arxiv.org/abs/2309.11406)).
  - *Contribution:* Presents challenge scenarios about schema changes in live programming and local-first software. It is not cited here as evidence about foreign-key orphan handling or general relational constraint preservation.
- **CR-SQLite (vlcn.io) / ElectricSQL / PowerSync:** See the official [cr-sqlite repository](https://github.com/vlcn-io/cr-sqlite), [ElectricSQL repository](https://github.com/electric-sql/electric), and [PowerSync project site](https://powersync.com/) for software references.
  - *Current Landscape:* CR-SQLite provides a loadable SQLite extension. ElectricSQL and PowerSync are separate local-first data synchronization projects; their architectures and product scopes evolve, and are not compared systematically here.
  - *Scope:* SemanticSync explores declarative, type-validated pairwise policies on SQLite. This selective review does not establish how common particular policies are in other systems or support a novelty claim.

---

## 2. Invariant-Preserving Replication Literature

A critical research area is preserving relational and numeric constraints under weak consistency:

- **Balegas et al. (2018)** — *IPA: Invariant-preserving Applications for Weakly-consistent Replicated Databases* ([arXiv:1802.08474](https://arxiv.org/abs/1802.08474)).
  - *Contribution:* Static analysis and runtime repair actions to uphold application correctness under weak consistency without full coordination.
  - *Relevance:* Supports SemanticSync's strategy of explicit conflict flagging (`REJECT`) and orphan quarantine rather than silent corruption.
- **Balegas et al. (2015)** — *Extending Eventually Consistent Cloud Databases for Enforcing Numeric Invariants* ([arXiv:1503.09052](https://arxiv.org/abs/1503.09052)).
  - *Contribution:* Bounded counters using escrow techniques to prevent numeric underflow (e.g., negative inventory or negative balance) under eventual consistency.
  - *Connection to SemanticSync:* Demonstrates that naive additive `SUM` ($base + \Delta A + \Delta B$) is unsafe under negative deltas without explicit boundary enforcement.
- **Lewchenko et al. (2018)** — *Conflict-Aware Replicated Data Types (CARDs)* ([arXiv:1802.08733](https://arxiv.org/abs/1802.08733)).
  - *Contribution:* CARDs use consistency guards (two-state predicates) to determine whether concurrent operations can proceed or must be flagged/blocked.

---

## 3. Source-grounded comparison (selective)

Only source-supported distinctions are included. `Unknown` means the examined sources do not establish the behavior; it is not evidence of absence.

| System / source | Data and merge model supported by source | Relation to SemanticSync | Unknown or not compared here |
|---|---|---|---|
| Synql (Ignat, Elvinger, Ba; DAIS 2024 paper and Springer record) | CRDT-based replicated relational database with integrity constraints; the paper describes compensating user modifications so the computed relational state reflects what users saw and changed. | Closely related to relational offline replication and integrity. | No head-to-head comparison; no novelty claim based on feature absence. |
| CRDV (Faria and Pereira; supplied 2025 paper PDF) | Two SQL-view layers over replicated relational state; the paper describes SQL-defined merge semantics/types and query optimization. | Directly relevant to SQL-expressed merge semantics; any novelty claim about declaring merge logic in SQL needs careful differentiation. | Performance and supported semantics are not independently reproduced here; publisher metadata still needs verification in the citation audit. |
| Eventually-Consistent Replicated Relations and Updatable Views (Thomassen and Yu; supplied 2023 PDF) | Delta-state CRDT approach for asynchronously replicated source relations and updatable views; the paper states an eventual-consistency guarantee for its model. | Related relational replication and view-update translation. | No direct implementation or performance comparison in this project. |
| Augmenting SQLite for Local-First Software (Tomter and Yu; supplied ADBIS 2021 proceedings PDF) | SQLite augmentation with conflict-free replicated relations; the supplied paper labels its implementation work in progress and says further features remain. | Directly related SQLite/local-first replication context. | Version-specific implementation status is not compared. |
| CR-SQLite (official project README, accessed 2026-10-20) | SQLite/libSQL extension for conflict-free replicated relations, with typed CRDT columns and a changes interface. The README distinguishes currently available types from work in progress and describes a causal event-log approach as future work. | Close software artifact for SQLite CRDT replication. | Current release feature status, constraints, and performance are not pinned or reproduced here. Do not characterize it as uniformly LWW or overwrite-only. |
| Electric (official `electric-sql/electric` README, accessed 2026-10-20) | Current repository describes Electric as a Postgres read-path sync engine with partial replication (“Shapes”) and HTTP delivery. | Related local-client data synchronization, with a different source database and protocol scope. | No benchmark or comparison of client write/conflict workflows. Older ElectricSQL architecture descriptions are not assumed current. |
| Antidote SQL (Lopes; supplied 2018 MSc thesis) | SQL interface for weakly consistent databases, per the thesis title and front matter. | Related SQL/weak-consistency system design. | No implementation or measurement comparison here. |
| Merge What You Can, Fork What You Can't (Schiefer, Litt, Jackson; supplied paper) | Local-first integrity model exposes multiple event histories for conflicting writes so users can manually reconcile while preserving constraints within each history. | Related integrity/conflict-review design; a different history model from row conflicts and quarantine. | No empirical or feature-completeness comparison. |
| ConLoc, LoRe, and No-Op invariant work (supplied papers) | The papers describe distinct invariant/safety approaches for local-first or weakly consistent systems. | Shows that invariant-aware local-first work is an active and close area. | No equivalence, implementation comparison, or novelty conclusion from title/abstract inspection alone. |
| SemanticSync (current repository) | Python/SQLite prototype with schema-assigned pairwise policies, tracked operations, enumerated FK quarantine paths, and checkpoint-backed compaction. | Evidence supports an implementation and finite tested behaviors. | No formal proof, broad convergence result, fair same-semantics performance comparison, or established novelty claim. |

## 4. Review status and citation caveats

The user-supplied 25-PDF collection is inventoried with file hashes in `research/audit/LOCAL_PAPER_INVENTORY.md`. An inventory does not validate publisher metadata or every claim in a paper. The current manuscript's comparison should remain selective and non-exhaustive. A source-level reference audit is tracked in `research/related_work/REFERENCE_VERIFICATION.md`; novelty questions are tracked in `research/related_work/NOVELTY_ASSESSMENT.md`.
