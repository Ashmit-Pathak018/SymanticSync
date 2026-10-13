"""Real SQLite replica workload and reproducible benchmark telemetry."""
from __future__ import annotations
import csv, json, os, platform, random, shutil, sqlite3, sys, tempfile, time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from backend.engine.crdt_sync import CRDTSyncEngine


@dataclass
class StressBenchmarkConfig:
    num_operations: int = 1000
    conflict_density: float = 0.20
    seed: int = 42
    output_dir: str | None = None


@dataclass
class StressBenchmarkResult:
    config: dict[str, Any]
    environment: dict[str, Any]
    num_operations: int
    conflict_density: float
    total_conflicts_evaluated: int
    baseline_scr: float
    semantic_sync_scr: float
    baseline_convergence_rate: float
    semantic_sync_convergence_rate: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    avg_latency_ms: float
    total_sync_time_ms: float
    resolution_overhead_ms: float
    change_log_entries: int
    artifacts: dict[str, str] = field(default_factory=dict)
    baseline_vra: float = 0.0
    semantic_sync_vra: float = 0.0
    baseline_sync_time_ms: float = 0.0
    semantic_sync_sync_time_ms: float = 0.0
    baseline_change_log_entries: int = 0
    semantic_sync_change_log_entries: int = 0
    workload_digest: str = ""

    def to_dict(self) -> dict[str, Any]: return asdict(self)


def get_environment_metadata() -> dict[str, Any]:
    return {"platform": platform.platform(), "python_version": sys.version,
            "machine": platform.machine(), "processor": platform.processor(), "pid": os.getpid()}


def _percentile(values: list[float], p: float) -> float:
    if not values: return 0.0
    vals = sorted(values); idx = max(0, min(len(vals)-1, int((len(vals)-1)*p)))
    return vals[idx]


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

    def _execute(self, root: Path, ops: list[dict[str, Any]], policies: dict[str, dict[str,str]]) -> dict[str, Any]:
        base = str(root/"base.db")
        with sqlite3.connect(base) as c:
            c.execute("CREATE TABLE bench_rows(id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
            c.executemany("INSERT INTO bench_rows VALUES (?,100)", ((i,) for i in range(1,len(ops)+1)))
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
        return {"paths":(a,b),"latencies":lat,"sync_ms":sync_ms,"values_a":va,"values_b":vb,
                "receipts":self._db_counts((a,b)),"sync":sync}

    def run_benchmark(self) -> StressBenchmarkResult:
        if self.config.num_operations not in (1000,5000,10000):
            raise ValueError("num_operations must be 1000, 5000, or 10000")
        if self.config.conflict_density not in (0.05,0.20,0.50):
            raise ValueError("conflict_density must be 0.05, 0.20, or 0.50")
        ops=self.generate_workload_operations(); conflicts=sum(o["is_conflict"] for o in ops)
        digest=__import__("hashlib").sha256(json.dumps(ops,sort_keys=True).encode()).hexdigest()
        scratch=Path(tempfile.mkdtemp(prefix=".semanticsync-bench-",dir=Path.cwd()))
        # Each run has its own isolated tree; place under workspace so Windows sandbox temp is not required.
        base_root=scratch
        (base_root/"baseline").mkdir(); (base_root/"semantic").mkdir()
        baseline=self._execute(base_root/"baseline",ops,{"bench_rows":{"value":"LWW"}})
        semantic=self._execute(base_root/"semantic",ops,{"bench_rows":{"value":"SUM"}})
        oracle=[o["expected_semantic"] if o["is_conflict"] else o["value_a"] for o in ops]
        # Workload is shuffled; arrays use row ID order.
        by_id=sorted(ops,key=lambda o:o["op_id"])
        oracle=[o["expected_semantic"] if o["is_conflict"] else o["value_a"] for o in by_id]
        def metrics(run:dict[str,Any])->tuple[float,float,float]:
            a,b=run["values_a"],run["values_b"]
            scr=sum(x==y for state in (a,b) for x,y in zip(state,oracle))/(2*len(oracle))*100
            cr=sum(x==y for x,y in zip(a,b))/len(a)*100
            eligible=[i for i,o in enumerate(by_id) if o["is_conflict"]]
            vra=(sum(state[i]==oracle[i] for state in (a,b) for i in eligible)/(2*len(eligible))*100) if eligible else 100.0
            return scr,cr,vra
        bs,bc,bv=metrics(baseline); ss,sc,sv=metrics(semantic)
        lat=semantic["latencies"]
        artifacts={}
        if self.config.output_dir:
            out=Path(self.config.output_dir); out.mkdir(parents=True,exist_ok=True)
            stem=f"benchmark_{self.config.num_operations}_{int(self.config.conflict_density*100)}pct_{self.config.seed}"
            jp=out/f"{stem}.json"; cp=out/f"{stem}.csv"
            payload={"config":asdict(self.config),"environment":get_environment_metadata(),"num_operations":len(ops),
              "conflict_density":self.config.conflict_density,"total_conflicts_evaluated":conflicts,
              "baseline_scr":round(bs,4),"semantic_sync_scr":round(ss,4),"baseline_convergence_rate":round(bc,4),
              "semantic_sync_convergence_rate":round(sc,4),"baseline_vra":round(bv,4),"semantic_sync_vra":round(sv,4),
              "p50_latency_ms":_percentile(lat,.50),"p95_latency_ms":_percentile(lat,.95),"p99_latency_ms":_percentile(lat,.99),
              "avg_latency_ms":sum(lat)/len(lat),"baseline_sync_time_ms":baseline["sync_ms"],"semantic_sync_sync_time_ms":semantic["sync_ms"],
              "total_sync_time_ms":semantic["sync_ms"],"resolution_overhead_ms":semantic["sync_ms"]-baseline["sync_ms"],
              "baseline_change_log_entries":baseline["receipts"],"semantic_sync_change_log_entries":semantic["receipts"],
              "change_log_entries":semantic["receipts"],"workload_digest":digest,"workload":ops,
              "oracle_values":oracle,"observed_states":{"baseline_a":baseline["values_a"],"baseline_b":baseline["values_b"],
                "semantic_a":semantic["values_a"],"semantic_b":semantic["values_b"]}}
            jp.write_text(json.dumps(payload,indent=2),encoding="utf-8")
            with cp.open("w",newline="",encoding="utf-8") as f:
                w=csv.writer(f); w.writerow(["record_type","metric","value"])
                for key,val in payload.items():
                    if isinstance(val,(str,int,float)): w.writerow(["metric",key,val])
                for i,value in enumerate(lat): w.writerow(["operation_latency_ms",i+1,value])
            artifacts={"json":str(jp),"csv":str(cp)}
        result=StressBenchmarkResult(config=asdict(self.config),environment=get_environment_metadata(),num_operations=len(ops),
          conflict_density=self.config.conflict_density,total_conflicts_evaluated=conflicts,baseline_scr=round(bs,4),semantic_sync_scr=round(ss,4),
          baseline_convergence_rate=round(bc,4),semantic_sync_convergence_rate=round(sc,4),p50_latency_ms=round(_percentile(lat,.5),4),
          p95_latency_ms=round(_percentile(lat,.95),4),p99_latency_ms=round(_percentile(lat,.99),4),avg_latency_ms=round(sum(lat)/len(lat),4),
          total_sync_time_ms=round(semantic["sync_ms"],4),resolution_overhead_ms=round(semantic["sync_ms"]-baseline["sync_ms"],4),
          change_log_entries=semantic["receipts"],artifacts=artifacts,baseline_vra=round(bv,4),semantic_sync_vra=round(sv,4),
          baseline_sync_time_ms=round(baseline["sync_ms"],4),semantic_sync_sync_time_ms=round(semantic["sync_ms"],4),
          baseline_change_log_entries=baseline["receipts"],semantic_sync_change_log_entries=semantic["receipts"],workload_digest=digest)
        import gc
        gc.collect()
        resolved = scratch.resolve()
        if resolved.parent == Path.cwd().resolve() and resolved.name.startswith(".semanticsync-bench-"):
            shutil.rmtree(resolved)
        return result
