# Preliminary Novelty Assessment

**Status:** Open; not a novelty claim for submission. Based on the current repository, selected supplied papers, and partial primary-source checks recorded in `REFERENCE_VERIFICATION.md` and `RELATED_WORK_MATRIX.md`.

## What already exists

The local paper collection includes CRDT-based relational replication with integrity constraints (Synql), SQL-view-based replicated merge/type definitions (CRDV), asynchronous replicated relations and updatable views, SQLite CRR augmentation, local-first history forking for integrity conflicts, and several invariant-aware or formally verified local-first models. CR-SQLite and Electric are active software projects with different data and sync models. These works make broad claims such as “first semantic merge policies for local-first relational databases” unsafe without a much deeper, current comparison.

## What SemanticSync currently demonstrates

The repository implements selected schema-assigned pairwise field policies on SQLite, tracked operation identities and conditional replay, durable review paths for selected conflicts, selected FK-dependent-row quarantine, and checkpoint-backed log compaction under explicit validation gates. The evidence is finite tests and small synthetic workloads. No mathematical convergence proof or new general merge algorithm has been established.

## Smallest defensible contribution

At present, describe SemanticSync as an engineering prototype that integrates policy dispatch, operation replay, relational quarantine, and conservative checkpoint-assisted log compaction behind a SQLite/FastAPI/Studio workflow, and report the enumerated tests and limitations. Whether this integration is research-significant or novel is not established by the current evidence.

## Evidence needed for a stronger contribution

1. Complete primary-source verification and section-level mapping for the closest systems, especially Synql, CRDV, CR-SQLite, replicated relations/views, ConLoc, LoRe, and No-Op.
2. A precise novelty statement that distinguishes schema policy configuration from SQL-defined merge logic, CRDT column types, and invariant-aware reconciliation.
3. Independent-seed benchmark trials and a same-semantics baseline before performance claims.
4. Formalized policy/operation assumptions and stronger state-machine testing before broad correctness claims.
5. Evidence for benefits beyond implementation convenience if making usability, productivity, or integration claims.

## Current recommendation

Do not claim a novel algorithm, unique feature set, superiority over CRDTs, or first-of-kind system. A cautious systems-artifact or experience report may be possible after reference, correctness, and experimental gaps are closed; direct venue suitability cannot be judged yet.
