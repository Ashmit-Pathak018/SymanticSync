import React, { useState, useEffect } from 'react';
import {
  RefreshCw,
  Zap,
  Play,
  GitBranch,
  Layers,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Sparkles,
  Info,
  Database,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Alert } from '../components/ui/Alert';
import { api } from '../services/api';

export function SyncHub() {
  const { databases, selectedDbId, setSelectedDbId, syncStatus, refreshState, refreshCounter } = useApp();

  // Sync execution state
  const [selectedDb, setSelectedDb] = useState(selectedDbId || '');
  const [replicas, setReplicas] = useState([]);
  const [replicaA, setReplicaA] = useState('');
  const [replicaB, setReplicaB] = useState('');
  const [runningSync, setRunningSync] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [syncError, setSyncError] = useState(null);

  // Controlled conflict generation state
  const [genTable, setGenTable] = useState('products');
  const [genRowId, setGenRowId] = useState('1');
  const [genColumn, setGenColumn] = useState('quantity');
  const [genValA, setGenValA] = useState('115');
  const [genValB, setGenValB] = useState('120');
  const [generating, setGenerating] = useState(false);
  const [genSuccess, setGenSuccess] = useState(null);
  const [genError, setGenError] = useState(null);

  const replicaReqRef = React.useRef(0);

  // When global workspace changes, synchronize selectedDb and clear stale results
  useEffect(() => {
    if (selectedDbId && selectedDbId !== selectedDb) {
      setSelectedDb(selectedDbId);
      setSyncResult(null);
      setSyncError(null);
      setGenSuccess(null);
      setGenError(null);
    }
  }, [selectedDbId]);

  // Load replicas whenever selectedDb or refreshCounter changes
  useEffect(() => {
    async function loadReplicas() {
      if (!selectedDb) {
        setReplicas([]);
        setReplicaA('');
        setReplicaB('');
        return;
      }
      const reqId = ++replicaReqRef.current;
      try {
        const reps = await api.getReplicas(selectedDb);
        if (reqId !== replicaReqRef.current) return;
        const repList = Array.isArray(reps) ? reps : [];
        setReplicas(repList);
        if (repList.length >= 2) {
          setReplicaA(repList[0].replica_id);
          setReplicaB(repList[1].replica_id);
        } else if (repList.length === 1) {
          setReplicaA(repList[0].replica_id);
          setReplicaB('');
        } else {
          setReplicaA('');
          setReplicaB('');
        }
      } catch (err) {
        if (reqId === replicaReqRef.current) {
          console.error('Failed to load replicas for sync:', err);
        }
      }
    }
    loadReplicas();
  }, [selectedDb, refreshCounter]);

  const handleRunSync = async (e) => {
    e.preventDefault();
    if (!selectedDb || !replicaA || !replicaB) {
      alert('Please select both Replica A and Replica B to run synchronization.');
      return;
    }
    setRunningSync(true);
    setSyncResult(null);
    setSyncError(null);

    try {
      const res = await api.runSync(selectedDb, replicaA, replicaB);
      setSyncResult(res);
      await refreshState();
    } catch (err) {
      setSyncError(err.data?.detail || err.message);
    } finally {
      setRunningSync(false);
    }
  };

  const handleGenerateConflict = async (e) => {
    e.preventDefault();
    if (!selectedDb || !replicaA || !replicaB) {
      alert('Please select a database and two replicas first.');
      return;
    }
    setGenerating(true);
    setGenSuccess(null);
    setGenError(null);

    try {
      // Parse numeric values if appropriate
      let valA = genValA;
      let valB = genValB;
      if (!isNaN(Number(genValA)) && genValA.trim() !== '') valA = Number(genValA);
      if (!isNaN(Number(genValB)) && genValB.trim() !== '') valB = Number(genValB);

      let rowId = isNaN(Number(genRowId)) ? genRowId : Number(genRowId);

      const res = await api.generateConflict({
        db_id: selectedDb,
        replica_a_id: replicaA,
        replica_b_id: replicaB,
        table: genTable.trim(),
        row_id: rowId,
        column: genColumn.trim(),
        value_a: valA,
        value_b: valB,
      });

      setGenSuccess(`Injected divergence on ${genTable}.${genColumn} (Row #${rowId}): Replica A='${valA}' vs Replica B='${valB}'`);
      await refreshState();
      setTimeout(() => setGenSuccess(null), 5000);
    } catch (err) {
      setGenError(err.data?.detail || err.message);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-text-primary">CRDT Synchronization Hub</h1>
          <p className="text-xs text-text-secondary mt-1">
            Execute 3-way synchronization across offline replicas using Hybrid Logical Clocks (HLC) and schema merge policies.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Badge variant="success" size="md">
            Engine: {syncStatus?.status || 'Ready'}
          </Badge>
          <span className="text-xs text-text-muted font-mono">
            {syncStatus?.server_time ? new Date(syncStatus.server_time).toLocaleTimeString() : ''}
          </span>
        </div>
      </div>

      {/* Topology Overview */}
      <div className="bg-white border border-border rounded-xl p-5 shadow-xs">
        <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
          Synchronization Topology
        </h2>
        <div className="flex flex-col md:flex-row items-center justify-between gap-4 bg-gray-50/70 p-4 rounded-lg border border-border/80">
          {/* Replica A Node */}
          <div className="flex-1 text-center bg-white p-3 rounded-lg border border-border shadow-2xs">
            <span className="text-[10px] uppercase font-bold text-primary tracking-wider">Replica Node A</span>
            <div className="text-xs font-mono font-bold text-text-primary mt-1 truncate">
              {replicaA || 'No replica selected'}
            </div>
            <span className="text-[10px] text-text-muted mt-0.5 block">Offline SQLite Local File</span>
          </div>

          {/* Sync Arrows */}
          <div className="flex flex-col items-center justify-center text-primary px-3">
            <div className="flex items-center gap-2">
              <RefreshCw className={`w-5 h-5 ${runningSync ? 'animate-spin' : ''}`} />
            </div>
            <span className="text-[10px] font-mono text-text-muted mt-1 uppercase font-semibold">
              3-Way CRDT Exchange
            </span>
          </div>

          {/* Base Database Node */}
          <div className="flex-1 text-center bg-white p-3 rounded-lg border border-primary/40 shadow-2xs">
            <span className="text-[10px] uppercase font-bold text-text-primary tracking-wider">Common Ancestor</span>
            <div className="text-xs font-mono font-bold text-primary mt-1 truncate">
              {selectedDb || 'Base Database'}
            </div>
            <span className="text-[10px] text-text-muted mt-0.5 block">Base SQLite Canonical Store</span>
          </div>

          {/* Sync Arrows */}
          <div className="flex flex-col items-center justify-center text-primary px-3">
            <div className="flex items-center gap-2">
              <RefreshCw className={`w-5 h-5 ${runningSync ? 'animate-spin' : ''}`} />
            </div>
            <span className="text-[10px] font-mono text-text-muted mt-1 uppercase font-semibold">
              HLC Reconciliation
            </span>
          </div>

          {/* Replica B Node */}
          <div className="flex-1 text-center bg-white p-3 rounded-lg border border-border shadow-2xs">
            <span className="text-[10px] uppercase font-bold text-primary tracking-wider">Replica Node B</span>
            <div className="text-xs font-mono font-bold text-text-primary mt-1 truncate">
              {replicaB || 'No replica selected'}
            </div>
            <span className="text-[10px] text-text-muted mt-0.5 block">Offline SQLite Local File</span>
          </div>
        </div>
      </div>

      {/* Main Grid: Sync Trigger & Controlled Divergence Generator */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Col: Run Synchronization */}
        <div className="space-y-4">
          <Card title="Execute Synchronization Pipeline">
            <form onSubmit={handleRunSync} className="space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-text-primary mb-1">
                  Target Database Workspace *
                </label>
                <select
                  value={selectedDb}
                  onChange={(e) => {
                    setSelectedDb(e.target.value);
                    setSelectedDbId(e.target.value);
                  }}
                  className="w-full border border-border rounded-md px-3 py-2 text-text-primary bg-white focus:ring-1 focus:ring-primary focus:outline-hidden"
                >
                  {databases.map((db) => (
                    <option key={db.id} value={db.id}>
                      {db.name} ({db.id})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-text-primary mb-1">
                    Replica Node A *
                  </label>
                  <select
                    value={replicaA}
                    onChange={(e) => setReplicaA(e.target.value)}
                    className="w-full font-mono border border-border rounded-md px-3 py-2 text-text-primary bg-white focus:ring-1 focus:ring-primary focus:outline-hidden"
                  >
                    {replicas.map((r) => (
                      <option key={r.replica_id} value={r.replica_id}>
                        {r.replica_id}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block font-semibold text-text-primary mb-1">
                    Replica Node B *
                  </label>
                  <select
                    value={replicaB}
                    onChange={(e) => setReplicaB(e.target.value)}
                    className="w-full font-mono border border-border rounded-md px-3 py-2 text-text-primary bg-white focus:ring-1 focus:ring-primary focus:outline-hidden"
                  >
                    {replicas.map((r) => (
                      <option key={r.replica_id} value={r.replica_id}>
                        {r.replica_id}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <Button
                type="submit"
                variant="primary"
                className="w-full py-2.5"
                icon={Play}
                loading={runningSync}
                disabled={!selectedDb || !replicaA || !replicaB || replicaA === replicaB}
              >
                {replicaA === replicaB
                  ? 'Select Two Distinct Replicas'
                  : 'Run Three-Way Semantic Sync'}
              </Button>
            </form>
          </Card>

          {syncError && (
            <Alert variant="danger" title="Sync Execution Error">
              {syncError}
            </Alert>
          )}

          {syncResult?.skipped_tables?.length > 0 && (
            <Alert variant="warning" title="Some Tables Were Not Synchronized">
              Unsupported tables with composite or missing primary keys: {syncResult.skipped_tables.join(', ')}.
              These tables were skipped and need a single-column primary key before SemanticSync can process them.
            </Alert>
          )}

          {syncResult?.rejected_operations?.length > 0 && (
            <Alert variant="warning" title="Some Operations Were Held">
              {syncResult.rejected_operations.length} operation(s) were not applied because their causal prerequisites or expected row state did not match. Retry after synchronizing prerequisites or review the listed operations.
            </Alert>
          )}

          {/* Sync Result Card */}
          {syncResult && (
            <Card title="Synchronization Execution Outcome" className="border-success/40">
              <div className="grid grid-cols-3 gap-3 mb-4 text-center">
                <div className="p-2.5 bg-gray-50 rounded-lg border border-border">
                  <span className="text-[10px] text-text-muted uppercase font-semibold">Total Conflicts</span>
                  <div className="text-lg font-bold text-text-primary mt-0.5">
                    {syncResult.total_conflicts}
                  </div>
                </div>

                <div className="p-2.5 bg-emerald-50 rounded-lg border border-emerald-200">
                  <span className="text-[10px] text-success uppercase font-semibold">Auto-Resolved</span>
                  <div className="text-lg font-bold text-success mt-0.5">
                    {syncResult.auto_resolved}
                  </div>
                </div>

                <div className="p-2.5 bg-rose-50 rounded-lg border border-rose-200">
                  <span className="text-[10px] text-danger uppercase font-semibold">Flagged Review</span>
                  <div className="text-lg font-bold text-danger mt-0.5">
                    {syncResult.flagged_for_review}
                  </div>
                </div>
              </div>

              <div className="text-xs text-text-muted mb-2 font-mono flex items-center justify-between">
                <span>Execution Duration: {syncResult.duration_ms?.toFixed(2)} ms</span>
                <span className={syncResult.skipped_tables?.length || syncResult.rejected_operations?.length ? 'text-warning font-semibold' : 'text-success font-semibold'}>
                  {syncResult.rejected_operations?.length ? 'Completed with Held Operations' : syncResult.skipped_tables?.length ? 'Completed with Unsupported Tables' : 'Sync Completed'}
                </span>
              </div>

              {/* Applied Changes List */}
              {syncResult.applied_changes && syncResult.applied_changes.length > 0 ? (
                <div className="border border-border rounded-lg overflow-hidden">
                  <div className="bg-gray-100/70 px-3 py-1.5 font-semibold text-text-primary text-[11px] uppercase">
                    Applied Changes to SQLite Replicas:
                  </div>
                  <div className="divide-y divide-border text-xs font-mono max-h-48 overflow-y-auto">
                    {syncResult.applied_changes.map((chg, i) => (
                      <div key={i} className="p-2.5 bg-white flex items-center justify-between">
                        <div>
                          <span className="font-bold text-text-primary">
                            {chg.table}.{chg.column}
                          </span>
                          <span className="text-text-muted ml-1.5">Row #{chg.row_id}</span>
                          <span className="text-primary font-semibold ml-2">
                            &rarr; {String(chg.resolved_value)}
                          </span>
                        </div>
                        <Badge variant="policy" size="sm">
                          {chg.policy}
                        </Badge>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="p-4 text-center text-xs text-text-muted bg-gray-50 rounded-lg">
                  {syncResult.skipped_tables?.length
                    ? 'No supported changes were applied. Review the unsupported-table warning above.'
                    : 'Replicas were already identical. Zero divergences found.'}
                </div>
              )}
            </Card>
          )}
        </div>

        {/* Right Col: Controlled Divergence Generator */}
        <div className="space-y-4">
          <Card
            title="Controlled Conflict Generator"
            subtitle="Simulate independent offline edits on two replicas without connectivity"
          >
            {genSuccess && (
              <Alert variant="success" title="Divergent Edit Injected" className="mb-4">
                {genSuccess}
              </Alert>
            )}

            {genError && (
              <Alert variant="danger" title="Conflict Generation Error" className="mb-4">
                {genError}
              </Alert>
            )}

            <form onSubmit={handleGenerateConflict} className="space-y-3.5 text-xs">
              <div className="grid grid-cols-3 gap-2.5">
                <div>
                  <label className="block font-semibold text-text-primary mb-1">
                    Table Name
                  </label>
                  <input
                    type="text"
                    required
                    value={genTable}
                    onChange={(e) => setGenTable(e.target.value)}
                    className="w-full font-mono border border-border rounded-md px-2.5 py-1.5 text-text-primary focus:ring-1 focus:ring-primary focus:outline-hidden"
                    placeholder="e.g. products"
                  />
                </div>

                <div>
                  <label className="block font-semibold text-text-primary mb-1">
                    Row ID (PK)
                  </label>
                  <input
                    type="text"
                    required
                    value={genRowId}
                    onChange={(e) => setGenRowId(e.target.value)}
                    className="w-full font-mono border border-border rounded-md px-2.5 py-1.5 text-text-primary focus:ring-1 focus:ring-primary focus:outline-hidden"
                    placeholder="e.g. 1"
                  />
                </div>

                <div>
                  <label className="block font-semibold text-text-primary mb-1">
                    Column
                  </label>
                  <input
                    type="text"
                    required
                    value={genColumn}
                    onChange={(e) => setGenColumn(e.target.value)}
                    className="w-full font-mono border border-border rounded-md px-2.5 py-1.5 text-text-primary focus:ring-1 focus:ring-primary focus:outline-hidden"
                    placeholder="e.g. quantity"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 bg-gray-50 p-3 rounded-lg border border-border">
                <div>
                  <label className="block font-semibold text-primary mb-1">
                    Replica A Value ({replicaA || 'Node A'})
                  </label>
                  <input
                    type="text"
                    required
                    value={genValA}
                    onChange={(e) => setGenValA(e.target.value)}
                    className="w-full font-mono bg-white border border-border rounded-md px-2.5 py-1.5 text-text-primary focus:ring-1 focus:ring-primary focus:outline-hidden"
                    placeholder="e.g. 115"
                  />
                </div>

                <div>
                  <label className="block font-semibold text-primary mb-1">
                    Replica B Value ({replicaB || 'Node B'})
                  </label>
                  <input
                    type="text"
                    required
                    value={genValB}
                    onChange={(e) => setGenValB(e.target.value)}
                    className="w-full font-mono bg-white border border-border rounded-md px-2.5 py-1.5 text-text-primary focus:ring-1 focus:ring-primary focus:outline-hidden"
                    placeholder="e.g. 120"
                  />
                </div>
              </div>

              <Button
                type="submit"
                variant="secondary"
                className="w-full"
                icon={Zap}
                loading={generating}
                disabled={!selectedDb || !replicaA || !replicaB}
              >
                Inject Divergent Edits into Replicas
              </Button>
            </form>
          </Card>

          {/* Educational Note */}
          <div className="p-4 bg-blue-50/70 border border-blue-200/60 rounded-xl text-xs space-y-2">
            <div className="flex items-center gap-1.5 text-primary font-bold">
              <Info className="w-4 h-4" />
              <span>How SemanticSync Evaluates Conflicts</span>
            </div>
            <p className="text-text-secondary leading-relaxed">
              When replicas edit the same row offline, traditional CRDT engines select one value arbitrarily using Last-Write-Wins (LWW).
              This guarantees <strong className="text-text-primary">convergence</strong> (both devices hold the same byte), but causes <strong className="text-danger">silent semantic data loss</strong> (e.g. 15 sold items are overwritten instead of combined!).
            </p>
            <p className="text-text-secondary leading-relaxed">
              SemanticSync inspects the column's assigned policy:
              under <code className="font-mono font-bold text-primary">SUM</code>, it calculates the additive delta from the common ancestor (<code className="font-mono">100 + 15 + 20 = 135</code>), achieving both convergence AND semantic correctness.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
