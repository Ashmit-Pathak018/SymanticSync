# Failure Model and Expected Outcomes

This file distinguishes supported/tested behavior from the stronger failure guarantees that remain outside current evidence.

| Scenario | Expected behavior in supported scope | Evidence boundary |
|---|---|---|
| Duplicate tracked INSERT/UPDATE/DELETE or bounded operation delivery | Deduplicate by stable operation identity/receipt; do not apply twice. | Selected relay/restart tests; not arbitrary concurrent or malformed histories. |
| Reordered operations from the same source | Validate source sequence/dependencies and row preconditions; preserve pending/rejected operations rather than silently overwrite. | Selected bounded and sync tests. Independent source sequences are not globally comparable. |
| Receiver has a divergent local row | Reject/preserve and surface conflict or rejected operation. | Selected tests; direct untracked edits cannot be reconstructed as operation history. |
| INSERT ignored/mutated by trigger | Verify stored complete row before receipt; rollback on mismatch. | Trigger regressions exercise selected SQLite trigger behavior. External trigger side effects are unsupported. |
| Foreign-key violation on received write | Reject atomically and do not create receipt. | Selected received INSERT/UPDATE tests and FK invariant suite. |
| Parent DELETE in covered tracked path | Quarantine supported dependent rows in transaction, perform delete, verify FK integrity; rollback if unsafe. | Tests cover selected nested/composite-FK/alternate-unique schemas and mutation paths. Unsupported schemas fail closed. |
| SQL-console write | Requires explicit write opt-in and uses connection FK enforcement, but does not create tracked operation history/quarantine or participate in the shared mutation lock. | Tested as an explicit limitation; outside replication/checkpoint guarantee. |
| Missing, corrupt, or ambiguous checkpoint store | Block recovery/pruning; do not recreate as authoritative. | Store corruption/loss and committed-state tests. Not certified for physical media failure. |
| Invalid snapshot/manifest/membership/ACK/tail evidence | Block that checkpoint before its ACK/log mutation; retain logs and report blocked checkpoint. | Selected snapshot binding, ACK preflight, malformed-tail, and isolation regressions. |
| Failure during per-replica prune or registry reconciliation | Preserve committed journal evidence; restart/retry should be idempotent for tested boundaries. | Explicit injected failures and restart tests; registry/SQLite are not one global transaction. |
| Post-manifest UPDATE/INSERT/DELETE tail | Replay-validate identity, sequence, dependency closure, row effects and final state against checkpoint snapshot before recovery proceeds. | Selected valid-tail and malformed-tail tests; not a general offline-history merge. |
| Post-manifest RESOLVE tail | Block and require manual review. | Explicitly unsupported for automatic replay. |
| Process termination/restart | Selected checkpoint journal recovery is tested. | Does not establish power-loss durability; SQLite/filesystem flush behavior is not certified. |
| Two server processes or external writer | Not supported by process-local lock; external connections may bypass tracked APIs. | No cross-process proof or test claim. |
| General arbitrary network delay/partition/N-replica history | No general guarantee. | Only explicit finite schedules are tested. |
