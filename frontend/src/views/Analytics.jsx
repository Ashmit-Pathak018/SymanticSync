import React, { useState, useEffect } from 'react';
import {
  Play,
  Cpu,
  Info,
  FileText,
  Download,
  Eye,
  X,
} from 'lucide-react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Alert } from '../components/ui/Alert';
import { api } from '../services/api';
import { useApp } from '../context/AppContext';

const DOMAIN_WORKLOADS = [
  {
    id: 'inventory',
    name: 'Inventory Stock & Prices',
    description: 'Additive quantities (SUM), description notes (APPEND), unit prices (AVG), SKU constraints (REJECT).',
  },
  {
    id: 'notes',
    name: 'Document Collaboration',
    description: 'Document body appends (APPEND), edit counters (SUM), author recency (LWW).',
  },
  {
    id: 'health',
    name: 'Healthcare Clinical Records',
    description: 'Vital sign averages (AVG), physician observations (APPEND), critical blood type locks (REJECT).',
  },
];

export function Analytics() {
  const { refreshCounter } = useApp();
  const [activeTab, setActiveTab] = useState('workloads'); // 'workloads' | 'stress' | 'artifacts'

  // Domain Workload State
  const [selectedWorkload, setSelectedWorkload] = useState('inventory');
  const [runningDomain, setRunningDomain] = useState(false);
  const [domainStatus, setDomainStatus] = useState(null);
  const [domainError, setDomainError] = useState(null);

  // Parametric Stress Benchmark State
  const [stressOps, setStressOps] = useState(1000);
  const [stressDensity, setStressDensity] = useState(0.20);
  const [stressSeed, setStressSeed] = useState(42);
  const [runningStress, setRunningStress] = useState(false);
  const [stressMetrics, setStressMetrics] = useState(null);
  const [stressError, setStressError] = useState(null);

  // Artifacts State
  const [artifacts, setArtifacts] = useState([]);
  const [loadingArtifacts, setLoadingArtifacts] = useState(false);
  const [artifactError, setArtifactError] = useState(null);
  const [previewArtifact, setPreviewArtifact] = useState(null);
  const [previewContent, setPreviewContent] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);

  // Load domain metrics and artifacts on mount or global refresh
  useEffect(() => {
    async function loadData() {
      try {
        const metricsRes = await api.getMetrics();
        if (metricsRes && typeof metricsRes === 'object') {
          const wlMap = metricsRes.workloads || metricsRes;
          if (wlMap.stress_latest) {
            setStressMetrics(wlMap.stress_latest);
          }
        }
      } catch (err) {
        console.error('Failed to load metrics:', err);
      }

      loadArtifactsList();
    }
    loadData();
  }, [refreshCounter, selectedWorkload]);

  const loadArtifactsList = async () => {
    setLoadingArtifacts(true);
    setArtifactError(null);
    try {
      const list = await api.getBenchmarkArtifacts();
      setArtifacts(Array.isArray(list) ? list : []);
    } catch (err) {
      setArtifactError(err.data?.detail || err.message);
    } finally {
      setLoadingArtifacts(false);
    }
  };

  const handleRunDomainBenchmark = async (wl = selectedWorkload) => {
    setRunningDomain(true);
    setDomainError(null);
    try {
      const res = await api.runBenchmark(wl);
      setDomainStatus(res?.evaluation_status === 'illustrative_unvalidated' ? res : null);
    } catch (err) {
      setDomainError(err.data?.detail || err.message);
    } finally {
      setRunningDomain(false);
    }
  };

  const handleRunStressBenchmark = async (e) => {
    if (e) e.preventDefault();
    setRunningStress(true);
    setStressError(null);
    try {
      const res = await api.runStressBenchmark({
        num_operations: Number(stressOps),
        conflict_density: Number(stressDensity),
        seed: Number(stressSeed),
        export_artifacts: true,
      });
      setStressMetrics(res);
      await loadArtifactsList();
    } catch (err) {
      setStressError(err.data?.detail || err.message);
    } finally {
      setRunningStress(false);
    }
  };

  const handleSelectWorkload = (wlId) => {
    setSelectedWorkload(wlId);
    setDomainStatus(null);
  };

  const handlePreviewArtifact = async (artifact) => {
    setPreviewArtifact(artifact);
    setPreviewLoading(true);
    setPreviewContent('');
    try {
      const url = api.getBenchmarkArtifactDownloadUrl(artifact.filename);
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to download artifact`);
      const text = await res.text();
      setPreviewContent(text);
    } catch (err) {
      setPreviewContent(`Error loading preview: ${err.message}`);
    } finally {
      setPreviewLoading(false);
    }
  };

  const activeWorkloadInfo = DOMAIN_WORKLOADS.find((w) => w.id === selectedWorkload);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Research Benchmark Dashboard</h1>
          <p className="text-xs text-text-secondary mt-1">
            Measured synthetic stress telemetry and access to saved artifacts. Domain-runner outputs are illustrative and excluded from empirical results.
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="inline-flex rounded-lg border border-border bg-gray-50/70 p-1 text-xs">
          <button
            type="button"
            onClick={() => setActiveTab('workloads')}
            className={`px-3 py-1.5 rounded-md font-medium transition-all ${
              activeTab === 'workloads'
                ? 'bg-white text-primary shadow-2xs font-semibold'
                : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            Domain Runner (Unvalidated)
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('stress')}
            className={`px-3 py-1.5 rounded-md font-medium transition-all ${
              activeTab === 'stress'
                ? 'bg-white text-primary shadow-2xs font-semibold'
                : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            Parametric Stress Harness
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('artifacts')}
            className={`px-3 py-1.5 rounded-md font-medium transition-all ${
              activeTab === 'artifacts'
                ? 'bg-white text-primary shadow-2xs font-semibold'
                : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            Matrix Artifacts ({artifacts.length})
          </button>
        </div>
      </div>

      {/* Mandatory Scientific Validity Notice */}
      <div className="bg-amber-50/60 border border-amber-200/70 rounded-xl p-4 text-xs text-text-primary flex items-start gap-3">
        <Info className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
        <div>
          <h4 className="font-bold text-amber-900 mb-0.5">
            Scientific Evaluation Boundary & Research Scope
          </h4>
          <p className="text-amber-800 leading-relaxed text-[11px]">
            The domain runner is a development-only resolver demonstration, not a validated comparison. Its former replica-B LWW proxy and hard-coded convergence values are unavailable and excluded from empirical results. The separate stress matrix measures sequential tracked writes followed by batch synchronization; it does not establish concurrent-writer performance or general convergence.
          </p>
        </div>
      </div>

      {/* ─────────────────────────────────────────────────────────────
          TAB 1: DOMAIN WORKLOADS
      ───────────────────────────────────────────────────────────── */}
      {activeTab === 'workloads' && (
        <div className="space-y-6">
          {/* Workload Selector Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {DOMAIN_WORKLOADS.map((wl) => {
              const isSelected = selectedWorkload === wl.id;
              return (
                <div
                  key={wl.id}
                  onClick={() => handleSelectWorkload(wl.id)}
                  className={`p-4 rounded-xl border transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-white border-primary shadow-xs ring-2 ring-primary/10'
                      : 'bg-white/70 border-border hover:bg-white hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="font-bold text-sm text-text-primary">{wl.name}</span>
                  </div>
                  <p className="text-xs text-text-secondary leading-relaxed line-clamp-2">
                    {wl.description}
                  </p>
                </div>
              );
            })}
          </div>

          <div className="flex justify-end">
            <Button
              variant="primary"
              icon={Play}
              loading={runningDomain}
              onClick={() => handleRunDomainBenchmark(selectedWorkload)}
            >
              Check Runner Status ({activeWorkloadInfo?.name})
            </Button>
          </div>

          {domainError && (
            <Alert variant="danger" title="Domain Benchmark Error">
              {domainError}
            </Alert>
          )}

          <div className="rounded-xl border border-amber-300 bg-amber-50 p-6 text-sm text-text-primary" role="status">
            <h2 className="font-bold text-amber-900">Domain runner is illustrative and unvalidated</h2>
            <p className="mt-2 leading-relaxed">
              This development endpoint does not run replica synchronization or a validated comparative experiment.
              Its former replica-B LWW proxy, resolver scores, timing values, and hard-coded convergence fields are
              unavailable. Domain-runner outputs are excluded from empirical results.
            </p>
            <p className="mt-2 text-xs text-text-secondary">
              Use the Parametric Stress Harness for its documented, limited telemetry. Its workload is sequential
              tracked writes followed by batch synchronization; it is not a concurrent-writer experiment.
            </p>
            {domainStatus && (
              <p className="mt-3 text-xs font-semibold" data-testid="domain-runner-status">
                Status checked for {domainStatus.workload}: {domainStatus.evaluation_status}
              </p>
            )}
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────
          TAB 2: PARAMETRIC STRESS HARNESS
      ───────────────────────────────────────────────────────────── */}
      {activeTab === 'stress' && (
        <div className="space-y-6">
          <Card
            title="Configure Parametric Stress Benchmark"
            subtitle="Evaluate 1,000 to 10,000 operations across 5% to 50% conflict densities with deterministic random seeds."
          >
            <form onSubmit={handleRunStressBenchmark} className="space-y-4 text-xs">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="block font-semibold text-text-primary mb-1">
                    Number of Operations
                  </label>
                  <select
                    value={stressOps}
                    onChange={(e) => setStressOps(Number(e.target.value))}
                    className="w-full font-mono border border-border rounded-md px-3 py-2 text-text-primary bg-white focus:ring-1 focus:ring-primary focus:outline-hidden"
                  >
                    <option value={1000}>1,000 operations (Fast validation)</option>
                    <option value={5000}>5,000 operations (Moderate load)</option>
                    <option value={10000}>10,000 operations (Full scale)</option>
                  </select>
                </div>

                <div>
                  <label className="block font-semibold text-text-primary mb-1">
                    Conflict Density
                  </label>
                  <select
                    value={stressDensity}
                    onChange={(e) => setStressDensity(Number(e.target.value))}
                    className="w-full font-mono border border-border rounded-md px-3 py-2 text-text-primary bg-white focus:ring-1 focus:ring-primary focus:outline-hidden"
                  >
                    <option value={0.05}>5% Conflict Density (Light contention)</option>
                    <option value={0.20}>20% Conflict Density (Nominal matrix)</option>
                    <option value={0.50}>50% Conflict Density (Heavy contention)</option>
                  </select>
                </div>

                <div>
                  <label className="block font-semibold text-text-primary mb-1">
                    Random Seed
                  </label>
                  <input
                    type="number"
                    value={stressSeed}
                    onChange={(e) => setStressSeed(Number(e.target.value))}
                    className="w-full font-mono border border-border rounded-md px-3 py-2 text-text-primary bg-white focus:ring-1 focus:ring-primary focus:outline-hidden"
                    placeholder="42"
                  />
                </div>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-border">
                <span className="text-[11px] text-text-muted">
                  Runs the full stress harness, records p50/p95/p99 latency distributions, and exports JSON/CSV artifacts.
                </span>
                <Button
                  type="submit"
                  variant="primary"
                  icon={Play}
                  loading={runningStress}
                >
                  Run Stress Benchmark
                </Button>
              </div>
            </form>
          </Card>

          {stressError && (
            <Alert variant="danger" title="Stress Benchmark Error">
              {stressError}
            </Alert>
          )}

          {/* Stress Results Display */}
          {stressMetrics ? (
            <div className="space-y-6">
              {/* Top Summary Banner */}
              <div className="bg-white border border-border rounded-xl p-6 shadow-xs">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-border gap-2">
                  <div>
                    <span className="text-xs uppercase font-bold text-primary tracking-wider">
                      Parametric Stress Matrix Outcome
                    </span>
                    <h2 className="text-lg font-bold text-text-primary mt-0.5">
                      {stressMetrics.num_operations?.toLocaleString()} Ops @ {(stressMetrics.conflict_density * 100)?.toFixed(0)}% Conflict Density
                    </h2>
                    <p className="text-xs text-text-secondary mt-0.5">
                      Seed: <code className="font-mono">{stressMetrics.config?.seed ?? stressSeed}</code> | Workload Digest: <code className="font-mono text-[10px]">{stressMetrics.workload_digest || 'synthetic-v1'}</code>
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="success" size="md">
                      Benchmark-row value agreement: {stressMetrics.semantic_sync_row_value_agreement_rate?.toFixed(1) ?? 'N/A'}%
                    </Badge>
                  </div>
                </div>

                {/* Primary Comparison Bars */}
                <div className="py-6 space-y-6 max-w-4xl">
                  {/* SCR */}
                  <div>
                    <div className="flex items-center justify-between text-xs font-semibold mb-1.5">
                      <span className="text-text-primary">Semantic Correctness Rate (SCR)</span>
                      <div className="space-x-3 text-xs font-mono">
                        <span className="text-warning">LWW: {typeof stressMetrics.baseline_scr === 'number' ? `${stressMetrics.baseline_scr.toFixed(1)}%` : 'N/A'}</span>
                        <span className="text-success font-bold">SemanticSync: {typeof stressMetrics.semantic_sync_scr === 'number' ? `${stressMetrics.semantic_sync_scr.toFixed(1)}%` : 'N/A'}</span>
                      </div>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-4 p-0.5 border border-border overflow-hidden flex">
                      <div
                        className="bg-success h-full rounded-full transition-all duration-700"
                        style={{ width: `${stressMetrics.semantic_sync_scr || 0}%` }}
                      />
                    </div>
                  </div>

                  {/* VRA */}
                  <div>
                    <div className="flex items-center justify-between text-xs font-semibold mb-1.5">
                      <span className="text-text-primary">Valid Resolution Accuracy (VRA)</span>
                      <div className="space-x-3 text-xs font-mono">
                        <span className="text-warning">LWW: {typeof stressMetrics.baseline_vra === 'number' ? `${stressMetrics.baseline_vra.toFixed(1)}%` : 'N/A'}</span>
                        <span className="text-success font-bold">
                          SemanticSync: {typeof stressMetrics.semantic_sync_vra === 'number' ? `${stressMetrics.semantic_sync_vra.toFixed(1)}%` : 'N/A'}
                        </span>
                      </div>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-4 p-0.5 border border-border overflow-hidden flex">
                      <div
                        className="bg-emerald-500 h-full rounded-full transition-all duration-700"
                        style={{ width: `${stressMetrics.semantic_sync_vra || 0}%` }}
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Latency & Hardware Metrics Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                <Card className="p-3 text-center">
                  <span className="text-[10px] uppercase font-bold text-text-muted">p50 Mutation</span>
                  <div className="text-lg font-bold text-text-primary font-mono mt-1">
                    {stressMetrics.p50_latency_ms !== undefined ? `${stressMetrics.p50_latency_ms.toFixed(2)} ms` : 'N/A'}
                  </div>
                  <span className="text-[10px] text-text-muted">Median per-op</span>
                </Card>

                <Card className="p-3 text-center">
                  <span className="text-[10px] uppercase font-bold text-text-muted">p95 Mutation</span>
                  <div className="text-lg font-bold text-text-primary font-mono mt-1">
                    {stressMetrics.p95_latency_ms !== undefined ? `${stressMetrics.p95_latency_ms.toFixed(2)} ms` : 'N/A'}
                  </div>
                  <span className="text-[10px] text-text-muted">95th pct per-op</span>
                </Card>

                <Card className="p-3 text-center">
                  <span className="text-[10px] uppercase font-bold text-text-muted">p99 Mutation</span>
                  <div className="text-lg font-bold text-text-primary font-mono mt-1">
                    {stressMetrics.p99_latency_ms !== undefined ? `${stressMetrics.p99_latency_ms.toFixed(2)} ms` : 'N/A'}
                  </div>
                  <span className="text-[10px] text-text-muted">Tail per-op</span>
                </Card>

                <Card className="p-3 text-center">
                  <span className="text-[10px] uppercase font-bold text-text-muted">Net Sync Δ</span>
                  <div className="text-lg font-bold text-text-primary font-mono mt-1">
                    {stressMetrics.resolution_overhead_ms !== undefined ? `${stressMetrics.resolution_overhead_ms.toFixed(3)} ms` : 'N/A'}
                  </div>
                  <span className="text-[10px] text-text-muted">Semantic batch − LWW batch</span>
                </Card>

                <Card className="p-3 text-center">
                  <span className="text-[10px] uppercase font-bold text-text-muted">Total Conflicts</span>
                  <div className="text-lg font-bold text-primary font-mono mt-1">
                    {stressMetrics.total_conflicts_evaluated?.toLocaleString() ?? 'N/A'}
                  </div>
                  <span className="text-[10px] text-text-muted">Divergences</span>
                </Card>

                <Card className="p-3 text-center">
                  <span className="text-[10px] uppercase font-bold text-text-muted">Change Log</span>
                  <div className="text-lg font-bold text-text-primary font-mono mt-1">
                    {stressMetrics.change_log_entries?.toLocaleString() ?? 'N/A'}
                  </div>
                  <span className="text-[10px] text-text-muted">CRDT events</span>
                </Card>
              </div>

              {/* Hardware / Environment Metadata */}
              {stressMetrics.environment && (
                <div className="p-4 bg-gray-50 border border-border rounded-xl text-xs space-y-2">
                  <h4 className="font-semibold text-text-primary">Environment & Reproducibility Telemetry</h4>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono text-[11px] text-text-secondary">
                    <div>Python: {stressMetrics.environment.python_version || '3.x'}</div>
                    <div>Platform: {stressMetrics.environment.platform || 'Windows'}</div>
                    <div>Processors: {stressMetrics.environment.cpu_count || 'Multi-core'}</div>
                    <div>Timestamp: {stressMetrics.environment.timestamp ? new Date(stressMetrics.environment.timestamp).toLocaleTimeString() : 'N/A'}</div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <Card className="text-center py-16">
              <Cpu className="w-12 h-12 text-text-muted mx-auto mb-3" />
              <h3 className="text-sm font-semibold text-text-primary">No Stress Benchmark Executed In This Session</h3>
              <p className="text-xs text-text-secondary max-w-md mx-auto mt-1 mb-5">
                Configure operation scale and conflict density above, or view recorded matrix artifacts in the Artifacts tab.
              </p>
              <Button
                variant="primary"
                icon={Play}
                loading={runningStress}
                onClick={handleRunStressBenchmark}
              >
                Run 1,000 Ops @ 20% Density
              </Button>
            </Card>
          )}
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────
          TAB 3: MATRIX ARTIFACTS REPOSITORY
      ───────────────────────────────────────────────────────────── */}
      {activeTab === 'artifacts' && (
        <div className="space-y-6">
          <Card
            title="Empirical Evaluation Artifacts Repository"
            subtitle="Raw JSON and CSV outputs generated from the 3x3 Phase 4 matrix evaluation (1k/5k/10k operations at 5%/20%/50% conflict density)."
          >
            {artifactError && (
              <Alert variant="danger" title="Artifact Discovery Error" className="mb-4">
                {artifactError}
              </Alert>
            )}

            {artifacts.length > 0 ? (
              <div className="border border-border rounded-lg overflow-hidden">
                <table className="w-full text-xs text-left">
                  <thead className="bg-gray-50 border-b border-border text-[11px] uppercase text-text-muted font-semibold">
                    <tr>
                      <th className="px-4 py-3">Artifact File</th>
                      <th className="px-3 py-3">Format</th>
                      <th className="px-3 py-3">Operations</th>
                      <th className="px-3 py-3">Conflict Density</th>
                      <th className="px-3 py-3">Seed</th>
                      <th className="px-3 py-3">Size</th>
                      <th className="px-4 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {artifacts.map((a, i) => (
                      <tr key={i} className="hover:bg-gray-50/70 transition-colors">
                        <td className="px-4 py-3 font-mono font-medium text-text-primary">
                          <div className="flex items-center gap-2">
                            <FileText className="w-4 h-4 text-text-muted flex-shrink-0" />
                            <span className="truncate max-w-xs">{a.filename}</span>
                          </div>
                        </td>
                        <td className="px-3 py-3 font-mono">
                          <Badge variant={a.format === 'json' ? 'primary' : 'warning'} size="sm">
                            {a.format.toUpperCase()}
                          </Badge>
                        </td>
                        <td className="px-3 py-3 font-mono text-text-primary">
                          {a.num_operations ? a.num_operations.toLocaleString() : '—'}
                        </td>
                        <td className="px-3 py-3 font-mono text-text-primary">
                          {a.conflict_density_pct !== null && a.conflict_density_pct !== undefined
                            ? `${a.conflict_density_pct}%`
                            : '—'}
                        </td>
                        <td className="px-3 py-3 font-mono text-text-secondary">
                          {a.seed ?? '—'}
                        </td>
                        <td className="px-3 py-3 font-mono text-text-muted text-[11px]">
                          {(a.size_bytes / 1024).toFixed(1)} KB
                        </td>
                        <td className="px-4 py-3 text-right space-x-2">
                          <Button
                            variant="outline"
                            size="sm"
                            icon={Eye}
                            onClick={() => handlePreviewArtifact(a)}
                          >
                            Preview
                          </Button>
                          <a
                            href={api.getBenchmarkArtifactDownloadUrl(a.filename)}
                            download={a.filename}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md border border-border bg-white text-text-primary hover:bg-gray-50 transition-colors"
                          >
                            <Download className="w-3.5 h-3.5" />
                            Download
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : loadingArtifacts ? (
              <div className="py-12 text-center text-xs text-text-muted">
                Scanning disk for benchmark artifacts...
              </div>
            ) : (
              <div className="py-12 text-center text-xs text-text-muted">
                No artifacts discovered in known directories. Run a stress benchmark above to generate JSON/CSV artifacts.
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Artifact Preview Modal */}
      {previewArtifact && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl border border-border max-w-4xl w-full max-h-[85vh] flex flex-col">
            <div className="px-5 py-4 border-b border-border flex items-center justify-between">
              <div>
                <h3 className="font-bold text-sm text-text-primary flex items-center gap-2">
                  <FileText className="w-4 h-4 text-primary" />
                  <span>{previewArtifact.filename}</span>
                </h3>
                <span className="text-[11px] text-text-muted font-mono">
                  {previewArtifact.format.toUpperCase()} | {(previewArtifact.size_bytes / 1024).toFixed(1)} KB
                </span>
              </div>
              <div className="flex items-center gap-2">
                <a
                  href={api.getBenchmarkArtifactDownloadUrl(previewArtifact.filename)}
                  download={previewArtifact.filename}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-primary text-white hover:bg-primary-hover"
                >
                  <Download className="w-3.5 h-3.5" />
                  Download File
                </a>
                <button
                  onClick={() => setPreviewArtifact(null)}
                  className="text-text-muted hover:text-text-primary p-1.5 rounded-md hover:bg-gray-100"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            <div className="flex-1 p-4 overflow-auto bg-gray-900 rounded-b-xl">
              {previewLoading ? (
                <div className="text-gray-400 font-mono text-xs">Loading artifact payload...</div>
              ) : (
                <pre className="text-emerald-400 font-mono text-[11px] leading-relaxed whitespace-pre-wrap select-text">
                  {previewContent}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
