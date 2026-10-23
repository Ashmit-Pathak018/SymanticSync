"""Real SQLite replica workload and reproducible benchmark telemetry."""
from __future__ import annotations
import csv, json, os, platform, random, shutil, sqlite3, statistics, sys, tempfile, time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from backend.engine.crdt_sync import CRDTSyncEngine
from backend.engine.fk_quarantine import connect_with_foreign_keys


@dataclass
class StressBenchmarkConfig:
    num_operations: int = 1000
    conflict_density: float = 0.20
    seed: int = 42
    trials: int = 2
    output_dir: str | None = None


@dataclass
class StressBenchmarkResult:
    config: dict[str, Any]
    environment: dict[str, Any]
    num_operations: int
    conflict_density: float
    total_conflicts_evaluated: int
    baseline_scr: float | None
    semantic_sync_scr: float | None
    baseline_row_value_agreement_rate: float
    semantic_sync_row_value_agreement_rate: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    avg_latency_ms: float
    total_sync_time_ms: float
    # Legacy field name: stores the batch-sync delta, not resolver-only overhead.
    resolution_overhead_ms: float
    change_log_entries: int
    artifacts: dict[str, str] = field(default_factory=dict)
    baseline_vra: float | None = None
    semantic_sync_vra: float | None = None
    baseline_sync_time_ms: float = 0.0
    semantic_sync_sync_time_ms: float = 0.0
    baseline_change_log_entries: int = 0
    semantic_sync_change_log_entries: int = 0
    workload_digest: str = ""
    trial_count: int = 1
    summary_statistics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]: return asdict(self)


def get_environment_metadata() -> dict[str, Any]:
    return {"platform": platform.platform(), "python_version": sys.version,
            "machine": platform.machine(), "processor": platform.processor(), "pid": os.getpid(),
            "sqlite_runtime_version": sqlite3.sqlite_version}


def aggregate_samples(values: list[float], unit: str) -> dict[str, Any]:
    """Return descriptive summaries without implying inferential significance."""
    if not values:
        return {"sample_count": 0, "unit": unit, "median": None, "minimum": None, "maximum": None}
    return {"sample_count": len(values), "unit": unit, "median": statistics.median(values),
            "minimum": min(values), "maximum": max(values)}


def _percentile(values: list[float], p: float) -> float:
    if not values: return 0.0
    vals = sorted(values); idx = max(0, min(len(vals)-1, int((len(vals)-1)*p)))
    return vals[idx]


def calculate_quality_metrics(
    values_a: list[int], values_b: list[int],
    operations: list[dict[str, Any]], oracle_values: list[int],
) -> dict[str, float | None]:
    """Score conflict outcomes and benchmark-row agreement from persisted values.

    SCR scores both replicas' final value for each generated conflict row only.
    RVAR is deliberately named row-value agreement: it compares only the ordered
    ``bench_rows.value`` observations, not complete SQLite database state.
    Metrics with no eligible conflicts are undefined and returned as ``None``.
    """
    row_count = len(operations)
    if len(values_a) != row_count or len(values_b) != row_count or len(oracle_values) != row_count:
        raise ValueError("Workload, oracle, and observed benchmark-row values must have equal length.")
    ordered = sorted(operations, key=lambda operation: int(operation["op_id"]))
    if [int(operation["op_id"]) for operation in ordered] != list(range(1, row_count + 1)):
        raise ValueError("Benchmark operation IDs must map one-to-one to ordered row positions.")

    conflict_positions = [index for index, operation in enumerate(ordered) if operation["is_conflict"]]
    scr = None
    vra = None
    if conflict_positions:
        correct_outcomes = sum(
            observed[index] == oracle_values[index]
            for index in conflict_positions
            for observed in (values_a, values_b)
        )
        scr = correct_outcomes / (2 * len(conflict_positions)) * 100.0

    row_agreement = (
        sum(left == right for left, right in zip(values_a, values_b)) / row_count * 100.0
        if row_count else 100.0
    )
    # This stress workload has no range or relational constraints; therefore it
    # cannot measure VRA. The domain harness reports validity separately.
    return {
        "scr": scr,
        "row_value_agreement_rate": row_agreement,
        "vra": vra,
    }


class StressHarness:
    """Compare actual LWW baseline sync with SemanticSync SUM replica sync."""
    def __init__(self, config: StressBenchmarkConfig) -> None:
        self.config = config
        self.rng = random.Random(config.seed)

    def generate_workload_operations(self) -> list[dict[str, Any]]:
        n = self.config.num_operations
        k = int(round(n*self.config.conflict_density))
        ops=[]
        for i in range(n):
            conflict = i < k
            da = self.rng.randint(1, 50)
            db = self.rng.randint(1, 50) if conflict else 0
            base = 100
            ops.append({"op_id": i+1, "is_conflict": conflict, "policy": "SUM",
                        "base_value": base, "delta_a": da, "delta_b": db,
                        "value_a": base+da, "value_b": base+db,
                        "expected_semantic": base+da+db})
        self.rng.shuffle(ops)
        return ops

    @staticmethod
    def _db_counts(paths: tuple[str, str]) -> int:
        total=0
        for path in paths:
            with sqlite3.connect(path) as c:
                row=c.execute("SELECT COUNT(*) FROM _ss_change_log").fetchone()
                total += int(row[0]) if row else 0
        return total

    @staticmethod
    def _values(paths: tuple[str, str], n: int) -> tuple[list[int], list[int]]:
        vals=[]
        for path in paths:
            with sqlite3.connect(path) as c:
                vals.append([int(r[0]) for r in c.execute("SELECT value FROM bench_rows ORDER BY id")])
        return vals[0], vals[1]

    @staticmethod
    def _initialize_base_database(base: Path, row_count: int) -> str:
        """Create a deterministic base image shared in shape/content by each pair."""
        with sqlite3.connect(base) as conn:
            # DELETE mode keeps the base image self-contained when create_replica
            # copies the SQLite file; also record the effective mode below.
            conn.execute("PRAGMA journal_mode=DELETE")
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            conn.execute("CREATE TABLE bench_rows(id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
            conn.executemany("INSERT INTO bench_rows VALUES (?,100)", ((i,) for i in range(1,row_count+1)))
        return str(journal_mode)

    def _execute(self, root: Path, ops: list[dict[str, Any]], policies: dict[str, dict[str,str]]) -> dict[str, Any]:
        root.mkdir(parents=True, exist_ok=True)
        base = str(root/"base.db")
        journal_mode=self._initialize_base_database(Path(base),len(ops))
        engine=CRDTSyncEngine(base_db_path=base, data_dir=str(root/"replicas"))
        a=engine.create_replica("bench_a"); b=engine.create_replica("bench_b")
        lat=[]
        for op in ops:
            start=time.perf_counter()
            engine.apply_change(a,"bench_a","bench_rows",op["op_id"],"value",op["value_a"])
            lat.append((time.perf_counter()-start)*1000)
            if op["is_conflict"]:
                start=time.perf_counter()
                engine.apply_change(b,"bench_b","bench_rows",op["op_id"],"value",op["value_b"])
                lat.append((time.perf_counter()-start)*1000)
        started=time.perf_counter()
        sync=engine.sync_replicas(a,b,base,"bench_a","bench_b",policies=policies)
        sync_ms=(time.perf_counter()-started)*1000
        va,vb=self._values((a,b),len(ops))
        replica_journal_modes=[]; replica_foreign_keys=[]
        for path in (a,b):
            with connect_with_foreign_keys(path) as conn:
                replica_journal_modes.append(conn.execute("PRAGMA journal_mode").fetchone()[0])
                replica_foreign_keys.append(conn.execute("PRAGMA foreign_keys").fetchone()[0])
        return {"paths":(a,b),"latencies":lat,"sync_ms":sync_ms,"values_a":va,"values_b":vb,
                "receipts":self._db_counts((a,b)),"sync":sync,"journal_mode":journal_mode,
                "replica_journal_modes":replica_journal_modes,"replica_foreign_keys":replica_foreign_keys}

    def run_benchmark(self) -> StressBenchmarkResult:
        if self.config.num_operations not in (1000,5000,10000):
            raise ValueError("num_operations must be 1000, 5000, or 10000")
        if self.config.conflict_density not in (0.0,0.05,0.20,0.50):
            raise ValueError("conflict_density must be 0, 0.05, 0.20, or 0.50")
        if isinstance(self.config.trials, bool) or not isinstance(self.config.trials, int) or not 2 <= self.config.trials <= 10:
            raise ValueError("trials must be an integer from 2 through 10 to balance execution order")
        ops=self.generate_workload_operations(); conflicts=sum(o["is_conflict"] for o in ops)
        digest=__import__("hashlib").sha256(json.dumps(ops,sort_keys=True).encode()).hexdigest()
        scratch=Path(tempfile.mkdtemp(prefix=".semanticsync-bench-",dir=Path.cwd()))
        # Each run has its own isolated tree; place under workspace so Windows sandbox temp is not required.
        base_root=scratch
        trials=[]
        # Alternate which implementation runs first. Each pair receives the exact
        # same immutable trace and a freshly initialized equivalent database.
        for trial_index in range(self.config.trials):
            trial_root=base_root/f"trial_{trial_index + 1}"
            trial_root.mkdir()
            first = "baseline" if trial_index % 2 == 0 else "semantic_sync"
            systems = {"baseline": {"policy": {"bench_rows":{"value":"LWW"}}, "result": None},
                       "semantic_sync": {"policy": {"bench_rows":{"value":"SUM"}}, "result": None}}
            for system in (first, "semantic_sync" if first == "baseline" else "baseline"):
                systems[system]["result"] = self._execute(
                    trial_root/system, ops, systems[system]["policy"]
                )
            baseline, semantic = systems["baseline"]["result"], systems["semantic_sync"]["result"]
            trials.append({"trial_index": trial_index + 1, "execution_order": [first,
                "semantic_sync" if first == "baseline" else "baseline"],
                "configuration": {"num_operations": self.config.num_operations,
                    "conflict_density": self.config.conflict_density, "seed": self.config.seed,
                    "trials":self.config.trials,"workload_digest": digest,
                    "policy_assignments":{"baseline":"LWW","semantic_sync":"SUM"},
                    "sync_mode":"sequential tracked writes followed by pairwise batch sync"},
                "journal_mode": {"base":baseline["journal_mode"],
                    "replicas":baseline["replica_journal_modes"]},
                "sqlite_foreign_keys_enabled":baseline["replica_foreign_keys"],
                "baseline": baseline, "semantic_sync": semantic})
        # Workload is shuffled; arrays use row ID order.
        by_id=sorted(ops,key=lambda o:o["op_id"])
        oracle=[o["expected_semantic"] if o["is_conflict"] else o["value_a"] for o in by_id]
        for trial in trials:
            for system in ("baseline", "semantic_sync"):
                run=trial[system]
                run["quality_metrics"]=calculate_quality_metrics(run["values_a"],run["values_b"],ops,oracle)
                run["tracked_write_latency_ms"]={"p50":_percentile(run["latencies"],.50),
                    "p95":_percentile(run["latencies"],.95),"p99":_percentile(run["latencies"],.99),
                    "mean":statistics.mean(run["latencies"]) if run["latencies"] else None}
        def samples(system: str, extract): return [extract(t[system]) for t in trials if extract(t[system]) is not None]
        summary={}
        for system in ("baseline", "semantic_sync"):
            summary[f"{system}_scr_pct"]=aggregate_samples(samples(system,lambda r:r["quality_metrics"]["scr"]),"percent")
            summary[f"{system}_row_value_agreement_pct"]=aggregate_samples(samples(system,lambda r:r["quality_metrics"]["row_value_agreement_rate"]),"percent")
            for percentile in ("p50","p95","p99","mean"):
                summary[f"{system}_tracked_write_{percentile}_ms"]=aggregate_samples(
                    samples(system,lambda r:r["tracked_write_latency_ms"][percentile]),"milliseconds")
            summary[f"{system}_batch_sync_ms"]=aggregate_samples(samples(system,lambda r:r["sync_ms"]),"milliseconds")
        summary["batch_sync_delta_ms"]=aggregate_samples(
            [t["semantic_sync"]["sync_ms"]-t["baseline"]["sync_ms"] for t in trials],"milliseconds")
        # Expose median values under stable top-level fields for API consumers.
        def med(name): return summary[name]["median"]
        bs=med("baseline_scr_pct") if conflicts else None
        ss=med("semantic_sync_scr_pct") if conflicts else None
        br=med("baseline_row_value_agreement_pct"); sr=med("semantic_sync_row_value_agreement_pct")
        bv=sv=None
        baseline_sync_ms=med("baseline_batch_sync_ms"); semantic_sync_ms=med("semantic_sync_batch_sync_ms")
        batch_delta_ms=med("batch_sync_delta_ms")
        baseline=trials[0]["baseline"]; semantic=trials[0]["semantic_sync"]
        lat=semantic["latencies"]
        env=get_environment_metadata()
        env["journal_mode"]="DELETE (verified for benchmark base and replica connections per trial)"
        env["measurement_scope"]="sequential replica-local writes followed by one batch synchronization per system per trial"
        artifacts={}
        if self.config.output_dir:
            out=Path(self.config.output_dir); out.mkdir(parents=True,exist_ok=True)
            stem=f"benchmark_{self.config.num_operations}_{int(self.config.conflict_density*100)}pct_{self.config.seed}"
            jp=out/f"{stem}.json"; cp=out/f"{stem}.csv"
            payload={"metric_version":"conflict-scr-row-agreement-v3-repeated",
              "metric_definitions":{"scr":"Correct final values for conflict rows only, scored across both replicas; null when no conflicts.",
                "row_value_agreement_rate":"Matching ordered bench_rows.value values across the two replicas; not full-database convergence.",
                "vra":"Not measured by this workload because it defines no domain range or relational constraints."},
              "config":asdict(self.config),"environment":env,"num_operations":len(ops),
              "initial_state":{"table":"bench_rows","row_count":len(ops),"value_for_every_row":100,
                "replicas_created_from_equivalent_fresh_base_per_trial":True},
              "trial_count":self.config.trials,"trials":[{k:v for k,v in t.items() if k not in ("baseline","semantic_sync")} | {
                  "sqlite_foreign_keys_enabled":t["baseline"]["replica_foreign_keys"],
                  "systems":{system:{"quality_metrics":t[system]["quality_metrics"],
                    "tracked_write_latency_ms":t[system]["tracked_write_latency_ms"],
                    "batch_sync_ms":t[system]["sync_ms"],"change_log_entries":t[system]["receipts"],
                    "observed_values_a":t[system]["values_a"],"observed_values_b":t[system]["values_b"]}
                    for system in ("baseline","semantic_sync")}} for t in trials],
              "summary_statistics":summary,"workload_mode":"sequential local writes followed by batch synchronization",
              "timing_boundaries":{"tracked_write_latency_ms":"wall time around each apply_change call, including local SQLite mutation and change-log capture; sequential calls",
                "batch_sync_ms":"wall time around sync_replicas only; excludes database creation and tracked writes",
                "batch_sync_delta_ms":"paired per-trial SemanticSync batch sync minus LWW batch sync"},
              "conflict_density":self.config.conflict_density,"total_conflicts_evaluated":conflicts,
              "conflict_row_ids":[o["op_id"] for o in by_id if o["is_conflict"]],
              "baseline_scr":round(bs,4) if bs is not None else None,
              "semantic_sync_scr":round(ss,4) if ss is not None else None,
              "baseline_row_value_agreement_rate":round(br,4),
              "semantic_sync_row_value_agreement_rate":round(sr,4),
              "baseline_vra":bv,"semantic_sync_vra":sv,
              "p50_latency_ms":med("semantic_sync_tracked_write_p50_ms"),"p95_latency_ms":med("semantic_sync_tracked_write_p95_ms"),"p99_latency_ms":med("semantic_sync_tracked_write_p99_ms"),
              "avg_latency_ms":med("semantic_sync_tracked_write_mean_ms"),"baseline_sync_time_ms":baseline_sync_ms,"semantic_sync_sync_time_ms":semantic_sync_ms,
              "total_sync_time_ms":semantic_sync_ms,"resolution_overhead_ms":batch_delta_ms,
              "baseline_change_log_entries":statistics.median(t["baseline"]["receipts"] for t in trials),"semantic_sync_change_log_entries":statistics.median(t["semantic_sync"]["receipts"] for t in trials),
              "change_log_entries":int(statistics.median(t["semantic_sync"]["receipts"] for t in trials)),"workload_digest":digest,"workload":ops,
              "oracle_values":oracle,"observed_states":{"baseline_a":baseline["values_a"],"baseline_b":baseline["values_b"],
                "semantic_a":semantic["values_a"],"semantic_b":semantic["values_b"]}}
            jp.write_text(json.dumps(payload,indent=2),encoding="utf-8")
            with cp.open("w",newline="",encoding="utf-8") as f:
                w=csv.writer(f); w.writerow(["record_type","trial_index","system","metric","value","unit","execution_order"])
                for key,val in payload.items():
                    if isinstance(val,(str,int,float)) or val is None:
                        w.writerow(["aggregate", "", "", key, "" if val is None else val, "", ""])
                for metric,stats in summary.items():
                    for statistic in ("sample_count","median","minimum","maximum"):
                        w.writerow(["summary", "", "", f"{metric}_{statistic}",
                            "" if stats[statistic] is None else stats[statistic],
                            stats["unit"] if statistic != "sample_count" else "trials", ""])
                for trial in trials:
                    order=" -> ".join(trial["execution_order"])
                    for key,value in trial["configuration"].items():
                        w.writerow(["trial_configuration",trial["trial_index"],"",key,value,"",order])
                    for system in ("baseline","semantic_sync"):
                        run=trial[system]
                        w.writerow(["trial",trial["trial_index"],system,"batch_sync_ms",run["sync_ms"],"milliseconds",order])
                        for percentile,value in run["tracked_write_latency_ms"].items():
                            w.writerow(["trial",trial["trial_index"],system,f"tracked_write_{percentile}",value,"milliseconds",order])
                        for i,value in enumerate(run["latencies"],1):
                            w.writerow(["tracked_write_sample",trial["trial_index"],system,f"write_{i}",value,"milliseconds",order])
            artifacts={"json":str(jp),"csv":str(cp)}
        result=StressBenchmarkResult(config=asdict(self.config),environment=env,num_operations=len(ops),
          conflict_density=self.config.conflict_density,total_conflicts_evaluated=conflicts,
          baseline_scr=round(bs,4) if bs is not None else None,
          semantic_sync_scr=round(ss,4) if ss is not None else None,
          baseline_row_value_agreement_rate=round(br,4),semantic_sync_row_value_agreement_rate=round(sr,4),p50_latency_ms=round(_percentile(lat,.5),4),
          p95_latency_ms=round(_percentile(lat,.95),4),p99_latency_ms=round(_percentile(lat,.99),4),avg_latency_ms=round(sum(lat)/len(lat),4),
          total_sync_time_ms=round(semantic_sync_ms,4),resolution_overhead_ms=round(batch_delta_ms,4),
          change_log_entries=semantic["receipts"],artifacts=artifacts,baseline_vra=bv,semantic_sync_vra=sv,
          baseline_sync_time_ms=round(baseline_sync_ms,4),semantic_sync_sync_time_ms=round(semantic_sync_ms,4),
          baseline_change_log_entries=int(statistics.median(t["baseline"]["receipts"] for t in trials)),
          semantic_sync_change_log_entries=int(statistics.median(t["semantic_sync"]["receipts"] for t in trials)),
          workload_digest=digest,trial_count=self.config.trials,summary_statistics=summary)
        import gc
        gc.collect()
        resolved = scratch.resolve()
        if resolved.parent == Path.cwd().resolve() and resolved.name.startswith(".semanticsync-bench-"):
            shutil.rmtree(resolved)
        return result
