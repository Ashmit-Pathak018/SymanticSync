# Artifact Path Migration

Project-owned local artifact directories with tool-generated `codex` names were moved to descriptive paths on 2026-10-19. A later provenance audit found that the optimized-matrix path combined two distinct datasets: the original optimized records in Git and later reruns produced after the SCR metric correction. Those 18 JSON/CSV files do not have identical contents or timings and must not be described as a path-only rename. No new benchmark was run during the provenance audit.

| Previous path | Current path | Contents |
|---|---|---|
| `.codex-bounded-check/` | `artifacts/test-evidence/bounded-policy-check/` | Bounded-policy test evidence |
| `.codex-phase3-final-review/` | `artifacts/test-evidence/phase3-final-review/` | Phase 3 final-review evidence |
| `.codex-phase3-full/` | `artifacts/test-evidence/phase3-full/` | Full Phase 3 test evidence |
| `.codex-phase4-matrix-20261013/` | `artifacts/benchmarks/historical-matrix-20261013/` | Historical single-run matrix |
| `.codex-phase4-optimized-matrix-20261013/` (original committed bytes) | `artifacts/benchmarks/historical-matrix-optimized-original-20261013/` | Original optimized matrix under its then-current metric definition; historical/superseded for conflict-only SCR |
| Later corrected-metric reruns previously placed at the same working-tree path | `artifacts/benchmarks/historical-matrix-optimized-metric-corrected-20261013/` | Separate rerun dataset, not byte-identical to the original optimized matrix |
| `.codex-phase4-repeated-20261014/` | `artifacts/benchmarks/repeated-stress-20261014/` | Nine paired repeated benchmark configurations |
| `.codex-pytest-tmp/` | `artifacts/test-evidence/pytest-temp-phase6/` | Preserved Phase 6 pytest temporary evidence |

References in the API artifact listing, benchmark validator, results protocol, changelog, implementation plan, limitations, testing strategy, traceability matrix, and manuscript were updated to use the current paths. The repeated-artifact validator can verify the preserved measurements without rerunning workloads:

```powershell
python -m backend.workloads.validate_repeated_benchmark_artifacts
```

The current audit compared all 18 original optimized JSON/CSV files against their Git blobs at `HEAD`; all 18 hashes matched the preserved `historical-matrix-optimized-original-20261013/` copies. All 18 corrected-metric files differ from the corresponding original files. This establishes preservation of the original bytes and confirms the corrected run is a distinct dataset. It does not independently revalidate the earlier claim that all 547 files across every migration path matched; remaining migration paths should be checked individually before making that broad statement.

Older Git commits may still contain the previous path names because this migration does not rewrite history. Embedded `output_dir` values in raw JSON may also name the original run path; these are historical run metadata, not active reproduction paths. They remain unchanged to preserve artifact bytes and provenance.

The raw JSON artifacts are intentionally byte-preserved. Their recorded `output_dir` fields name the original run locations, including former local artifact paths; these fields are historical run metadata, not active source-code or reproduction paths. Editing them would change saved artifact bytes and hashes, so the migration leaves that provenance intact.
