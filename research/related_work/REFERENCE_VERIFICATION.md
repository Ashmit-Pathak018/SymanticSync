# Reference Verification Register

**Audit date:** 2026-10-20
**Scope:** 22 entries in the current manuscript reference list. The user's PDF collection at `C:\Users\ASMIT\Downloads\DBMS-REVIEWPAPERS` was read locally; official publisher, arXiv, or project sources were consulted for selected items. This pass is not a complete line-by-line citation audit.

Status meanings: **VERIFIED** = primary/authoritative record and/or paper checked for the listed metadata; **PARTIAL** = some metadata checked but not all fields or claim support; **UNVERIFIED** = no adequate source check yet. None of these statuses establishes that every in-text statement citing the work is correct.

| # | Manuscript reference | Evidence checked in this pass | Status / remaining check |
|---:|---|---|---|
| 1 | Balegas et al. (2015), numeric invariants | Official arXiv record for 1503.09052 confirms title, author order and spelling (including **Mahsa Najafzadeh**), submission date (31 Mar 2015), and abstract-level bounded-counter/escrow description. The BibTeX first name was corrected from “Maryam” to “Mahsa.” | PARTIAL. The arXiv preprint metadata is verified; no final PVLDB version was verified in this pass. Map each manuscript claim to the paper's relevant sections before relying on stronger technical details. |
| 2 | Balegas et al. (2018), IPA | Official PVLDB PDF search result showed title, authors, volume/pages and DOI 10.14778/3297753.3297760. | PARTIAL. Verify all author order against issue metadata and map manuscript claim to exact sections. |
| 3 | Spanner (2013) | BibTeX/manuscript entry only. | UNVERIFIED. Check ACM publisher record and full author list if retained in abbreviated style. |
| 4 | Dynamo (2007) | BibTeX/manuscript entry only. | UNVERIFIED. Check ACM/SOSP primary record and full author list if retained in abbreviated style. |
| 5 | Edwards, Petricek, van der Storm (2023), “Live & Local Schema Change: Challenge Problems” | Official arXiv record for 2309.11406 reports exactly these three authors, title, and 2023 date. | VERIFIED for title/authors/year/arXiv identifier. This record is not a foreign-key/quarantine paper. |
| 6 | Gomes et al. (2017), strong eventual consistency verification | BibTeX/manuscript entry only in this pass. | UNVERIFIED. Check PACMPL/OOPSLA primary record and the exact theorem/model described by the paper. |
| 7 | Kleppmann and Beresford (2017), replicated JSON datatype | BibTeX/manuscript entry only. | UNVERIFIED. Check IEEE publisher record and claim support. |
| 8 | Kleppmann et al. (2019), local-first software | BibTeX/manuscript entry only. | UNVERIFIED. Check ACM Onward! record and ensure the cited passage supports the stated principles. |
| 9 | Kulkarni et al. (2014), “Logical Physical Clocks” | Springer OPODIS 2014 proceedings record confirms title, author list, and pp. 17–32; supplied Buffalo technical-report PDF uses expanded title “Logical Physical Clocks and Consistent Snapshots in Globally Distributed Databases” and spells the author “Deepak Madeppa.” | VERIFIED for the proceedings entry as cited; keep report as a separate version/title. The report/proceedings must not be merged into one bibliographic record. |
| 10 | Lewchenko et al. (2018), CARDs | BibTeX/manuscript entry only. | UNVERIFIED. Check arXiv 1802.08733 metadata and paper's exact guard semantics. |
| 11 | Shapiro et al. (2011), CRDTs | BibTeX/manuscript entry only. | UNVERIFIED. Check the SSS 2011 proceedings and exact formal results before using theorem-level wording. |
| 12 | `cr-sqlite` | Official `vlcn-io/cr-sqlite` repository is live and identifies the project as a SQLite/libSQL replication extension. Repository README version status is mutable; it advises using a release tag for stable builds. | PARTIAL. Suitable as a software citation with access date; pin a release/commit if the manuscript makes version-specific feature claims. |
| 13 | Electric / ElectricSQL | Official `electric-sql/electric` repository was inspected; current README describes Electric as a Postgres read-path sync engine using partial replication/Shapes. | PARTIAL. Software URL is valid, but cite current project name/version and do not reuse older active-active SQLite architecture claims without dating/versioning them. |
| 14 | Ignat, Elvinger, Ba (2024), Synql | Supplied 18-page PDF confirms title/authors and describes a CRDT relational approach; Springer DAIS 2024 record confirms conference, authors, pages 18–35. DOI 10.1007/978-3-031-62638-8_2 is on publisher proceedings record. | VERIFIED for core metadata. Technical comparisons still need section-level source mapping. |
| 15 | Faria and Pereira (2025), CRDV | Supplied published PDF confirms Nuno Faria and José Pereira, title, PACM Management of Data 3(1) / SIGMOD, Article 25, February 2025, 27 pages, DOI 10.1145/3709675; pp. 1–2 describe SQL-view-defined merge semantics and types. | VERIFIED against the supplied published paper for these fields and the cited technical summary. A separate ACM landing-page check was not performed. |
| 16 | Thomassen and Yu (2023), replicated relations/updatable views | Supplied PDF confirms title/authors and explains delta-state CRDT updates to asynchronously replicated source data and views. | PARTIAL. Verify Springer volume/chapter/pages/DOI and exact formal guarantee against publisher record. |
| 17 | Lopes (2018), Antidote SQL thesis | Supplied thesis front matter confirms author, title, MSc dissertation, institution context, adviser, and December 2018. | PARTIAL. Verify repository handle resolves to the same thesis and confirm exact school-name styling. |
| 18 | Schiefer, Litt, Jackson (2022), “Merge What You Can…” | Supplied PDF confirms title/authors and multiple-history/manual reconciliation approach. | PARTIAL. Verify PaPoC/ACM proceedings metadata, DOI and pages. |
| 19 | Köhler et al. (2025), ConLoc | Supplied PDF confirms title/authors and journal issue opening page. | PARTIAL. Verify IEEE DOI/volume/page metadata and exact claim support. |
| 20 | Haas et al. (2024), LoRe | Supplied PDF confirms title and authors. | PARTIAL. Verify ACM TOPLAS publisher metadata, DOI, volume/issue/article pages and claim support. |
| 21 | Borrego et al. (2025), “Ensuring Convergence and Invariants Without Coordination” | Supplied PDF confirms title/authors and No-Op framework at a high level. | PARTIAL. Verify final ECOOP/LIPIcs record and exact model/result statements with publisher source. |
| 22 | Litt et al. (2023), Riffle | Supplied 16-page PDF's ACM reference block identifies Geoffrey Litt, Nicholas Schiefer, Johannes Schickling, and Daniel Jackson; UIST '23; DOI 10.1145/3586183.3606801. Abstract and §§1–3 describe reactive relational application state in a local-first architecture. | VERIFIED for metadata and the bounded technical summary from the supplied published paper. This is adjacent application-state work, not a direct conflict-policy comparison; no absence-of-feature claim is inferred. |

## Attribution conflict: schema-change paper

The current manuscript and bibliography identify arXiv:2309.11406 as “Live & Local Schema Change: Challenge Problems” by Jonathan Edwards, Tomas Petricek, and Tijs van der Storm. The official arXiv record confirms that metadata. No “Marr et al.” attribution for that identifier appears in the current repository. The same title/identifier cannot be assigned to Marr et al. based on the evidence available here. If another Marr work was intended, its exact title or identifier is needed; until then the manuscript attribution should remain Edwards et al.

## Bibliography consistency observations

- The Markdown manuscript has 21 numbered references; the LLNCS BibTeX bibliography has corresponding entries including two software references. A mechanical key-to-citation check is still needed before final submission.
- The HLC proceedings paper and expanded-title University at Buffalo technical-report PDF are two versions. Cite one as the main proceedings item; list the report separately only if its distinct contents are discussed.
- `cr-sqlite` and Electric are software sources, not peer-reviewed papers. Current mutable repository state does not support release-specific claims without a tag or commit.
- The 25 supplied PDFs include relevant works not currently in the bibliography. Their presence does not imply they must all be cited; selection needs a documented relevance rationale.
- Do not add DOI or venue data for PARTIAL/UNVERIFIED entries until checked against the original publisher/official repository.

### Correction made after primary-source check

The arXiv record for [1503.09052](https://arxiv.org/abs/1503.09052) lists **Mahsa Najafzadeh**, not Maryam Najafzadeh. The LLNCS BibTeX author field now matches that record. This verifies the preprint's listed authorship and abstract-level description only; it does not establish a separate final proceedings or journal version.

## Additional section-level source mapping

The supplied local papers were used to bound related-work wording in `RELATED_WORK_MATRIX.md`: Synql abstract/intro; CRDV pp. 1–2 and its reference block; Thomassen and Yu abstract/§2; “Merge What You Can…” abstract/§2; and ConLoc abstract/intro. These checks support the stated high-level summaries only. They do not establish exhaustive comparisons, implementation equivalence, performance rankings, or absence of features in another system.
