import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  RefreshCw,
  Zap,
  Play,
  Layers,
  ShieldCheck,
  AlertTriangle,
  Info,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Alert } from '../components/ui/Alert';
import { api } from '../services/api';

export function SyncHub() {
  const navigate = useNavigate();
  const { databases, selectedDbId, setSelectedDbId, syncStatus, refreshState, refreshCounter } = useApp();

  // Sync execution state
  const [selectedDb, setSelectedDb] = useState(selectedDbId || '');
  const [replicas, setReplicas] = useState([]);
  const [replicaLoadError, setReplicaLoadError] = useState(null);
  const [replicaA, setReplicaA] = useState('');
  const [replicaB, setReplicaB] = useState('');
  const [tombstonePolicy, setTombstonePolicy] = useState('FLAG_FOR_REVIEW');
  const [runningSync, setRunningSync] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [syncError, setSyncError] = useState(null);
  const [remainingConflictCount, setRemainingConflictCount] = useState(null);
  const [conflictRefreshError, setConflictRefreshError] = useState(null);

  // Checkpoint & Compaction state
  const [compacting, setCompacting] = useState(false);
  const [compactResult, setCompactResult] = useState(null);
  const [compactError, setCompactError] = useState(null);
  const [initializingStore, setInitializingStore] = useState(false);
  const [storeFeedback, setStoreFeedback] = useState(null);

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
      setRemainingConflictCount(null);
      setConflictRefreshError(null);
      setGenSuccess(null);
      setGenError(null);
    }
  }, [selectedDbId]);

  // Load replicas whenever selectedDb or refreshCounter changes
  useEffect(() => {
    async function loadReplicas() {
      if (!selectedDb) {
        setReplicas([]);
        setReplicaLoadError(null);
        setReplicaA('');
        setReplicaB('');
        return;
      }
      const reqId = ++replicaReqRef.current;
      setReplicaLoadError(null);
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
          setReplicas([]);
          setReplicaA('');
          setReplicaB('');
          setReplicaLoadError(err.message || 'Could not load replicas.');
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
    setRemainingConflictCount(null);
    setConflictRefreshError(null);

    try {
      const res = await api.runSync(selectedDb, replicaA, replicaB, tombstonePolicy);
      setSyncResult(res);
      try {
        // Sync returns held conflict IDs, while the review screen reads the
        // durable conflict registry. Detect after sync so resolved cases do not
        // leave stale pre-sync review records.
        const remaining = await api.detectConflicts(selectedDb, replicaA, replicaB);
        setRemainingConflictCount(Array.isArray(remaining) ? remaining.length : 0);
      } catch (detectError) {
        setConflictRefreshError(detectError.data?.detail || detectError.message);
      }
      await refreshState();
    } catch (err) {
      setSyncError(err.data?.detail || err.message);
    } finally {
      setRunningSync(false);
    }
  };

  const handleInitStore = async () => {
    setInitializingStore(true);
    setStoreFeedback(null);
    try {
      const res = await api.initCheckpointStore();
      setStoreFeedback({
        type: res.status === 'ready' ? 'success' : 'error',
        message: res.status === 'ready'
          ? `Checkpoint store provisioned successfully (Store ID: ${res.store_id || 'active'}).`
          : `Checkpoint store initialization blocked: ${res.reason || 'Safety criteria not met.'}`,
      });
      await refreshState();
    } catch (err) {
      setStoreFeedback({
        type: 'error',
        message: err.data?.detail || err.message,
      });
    } finally {
      setInitializingStore(false);
    }
  };

  const handleCompact = async () => {
    if (!selectedDb) {
      alert('Please select a database workspace first.');
      return;
    }
    setCompacting(true);
    setCompactResult(null);
    setCompactError(null);
    try {
      const res = await api.compactSyncLogs(selectedDb);
      setCompactResult(res);
      await refreshState();
    } catch (err) {
      setCompactError(err.data?.detail || err.message);
    } finally {
      setCompacting(false);
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

      await api.generateConflict({
        db_id: selectedDb,
        replica_a_id: replicaA,
        replica_b_id: replicaB,
        table: genTable.trim(),
        row_id: rowId,
        column: genColumn.trim(),
        value_a: valA,
        value_b: valB,
      });

      setGenSuccess(`Tracked divergence recorded on ${genTable}.${genColumn} (row ${rowId}): A=${String(valA)}, B=${String(valB)}. The writes were issued sequentially before batch sync.`);
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
          <h1 className="text-xl font-bold text-text-primary">Replica Sync Hub</h1>
          <p className="text-xs text-text-secondary mt-1">
            Compare two selected replicas with their common base. The demonstration generator records tracked writes sequentially, then this action runs batch synchronization.
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
              Pairwise sync against the common base
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

              <div>
                <label className="block font-semibold text-text-primary mb-1">
                  Tombstone Merge Policy (Concurrent Delete/Update)
                </label>
                <select
                  value={tombstonePolicy}
                  onChange={(e) => setTombstonePolicy(e.target.value)}
                  className="w-full border border-border rounded-md px-3 py-2 text-text-primary bg-white focus:ring-1 focus:ring-primary focus:outline-hidden"
                >
                  <option value="FLAG_FOR_REVIEW">FLAG_FOR_REVIEW (Hold for human decision)</option>
                  <option value="DELETE_WINS">DELETE_WINS (Deletion takes precedence over update)</option>
                  <option value="UPDATE_RESURRECTS">UPDATE_RESURRECTS (Update resurrects deleted record)</option>
                </select>
                <p className="text-[11px] text-text-muted mt-1">
                  Governs how the resolver reconciles concurrent mutations where one replica modifies a row and another deletes it.
                </p>
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
                  : 'Run Pairwise Semantic Sync'}
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
                <span className={syncResult.skipped_tables?.length || syncResult.rejected_operations?.length || syncResult.flagged_for_review ? 'text-warning font-semibold' : 'text-success font-semibold'}>
                  {syncResult.rejected_operations?.length || syncResult.flagged_for_review ? 'Completed with Items for Review' : syncResult.skipped_tables?.length ? 'Completed with Unsupported Tables' : 'Sync Completed'}
                </span>
              </div>

              {conflictRefreshError ? (
                <Alert variant="warning" title="Conflict review list could not be refreshed" className="mb-4">
                  Sync returned its result, but the separate conflict registry refresh failed: {conflictRefreshError}. Check the API, then refresh the Conflicts screen.
                </Alert>
              ) : remainingConflictCount !== null ? (
                <Alert variant={remainingConflictCount ? 'warning' : 'success'} title={remainingConflictCount ? 'Remaining conflicts saved for review' : 'No conflicting values remain'} className="mb-4">
                  {remainingConflictCount} conflict record(s) were detected after synchronization.{' '}
                  {remainingConflictCount > 0 && <button type="button" className="underline font-semibold" onClick={() => navigate('/conflicts')}>Open Conflicts</button>}
                </Alert>
              ) : null}

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
            title="Controlled Tracked Divergence"
            subtitle="Record one tracked edit on Replica A, then one on Replica B; synchronize afterward"
          >
            {replicaLoadError && <Alert variant="danger" title="Replica list unavailable" className="mb-4">{replicaLoadError} Refresh or check the backend before generating edits.</Alert>}
            {genSuccess && (
              <Alert variant="success" title="Tracked Edits Recorded" className="mb-4">
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
                disabled={!selectedDb || !replicaA || !replicaB || Boolean(replicaLoadError)}
              >
                Record Two Tracked Edits
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
              An <code className="font-mono font-bold">LWW</code> policy selects one candidate value. In the seeded additive example, choosing 115 or 120 would omit the other replica's tracked change. With the shared base of 100, the configured <code className="font-mono font-bold text-primary">SUM</code> policy can combine the two deltas to produce 135.
            </p>
            <p className="text-text-secondary leading-relaxed">
              This is an illustration of the configured policy on this tracked scenario; it does not establish correctness or convergence for arbitrary histories or schedules.
            </p>
          </div>
        </div>
      </div>

      {/* Operational Checkpoints & Causal Compaction Section */}
      <Card
        title="Operational Checkpoints & Causal Compaction"
        subtitle="Advanced log-retention controls. Review checkpoint status before requesting compaction; this is not a demo reset, and recovery guarantees are limited to the documented tested scope."
      >
        <div className="space-y-4">
          {/* Status Row */}
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
            <div className="p-3 bg-gray-50 border border-border rounded-lg">
              <span className="text-[10px] uppercase font-semibold text-text-muted">Journal Store Status</span>
              <div className="flex items-center gap-2 mt-1">
                <Badge
                  variant={
                    syncStatus?.checkpoint_store?.status === 'ready'
                      ? 'success'
                      : syncStatus?.checkpoint_store?.status === 'blocked'
                      ? 'danger'
                      : 'warning'
                  }
                  size="md"
                >
                  {syncStatus?.checkpoint_store?.status?.toUpperCase() || 'UNINITIALIZED'}
                </Badge>
              </div>
            </div>

            <div className="p-3 bg-gray-50 border border-border rounded-lg">
              <span className="text-[10px] uppercase font-semibold text-text-muted">Store ID</span>
              <div className="text-xs font-mono font-bold text-text-primary mt-1 truncate">
                {syncStatus?.checkpoint_store?.store_id || 'Not Adopted'}
              </div>
            </div>

            <div className="p-3 bg-gray-50 border border-border rounded-lg">
              <span className="text-[10px] uppercase font-semibold text-text-muted">Stable Horizon</span>
              <div className="text-xs font-mono font-bold text-text-primary mt-1">
                {compactResult?.stable_horizon
                  ? `[${compactResult.stable_horizon.join(', ')}]`
                  : syncStatus?.checkpoint_store?.stable_horizon
                  ? `[${syncStatus.checkpoint_store.stable_horizon.join(', ')}]`
                  : 'No Compaction Horizon'}
              </div>
            </div>

            <div className="p-3 bg-gray-50 border border-border rounded-lg">
              <span className="text-[10px] uppercase font-semibold text-text-muted">Enrolled Replicas</span>
              <div className="text-xs font-bold text-text-primary mt-1">
                {replicas.length} Active / {syncStatus?.registered_replicas || 0} Registered
              </div>
            </div>
          </div>

          {/* Feedback Alerts */}
          {storeFeedback && (
            <Alert
              variant={storeFeedback.type === 'success' ? 'success' : 'danger'}
              title={storeFeedback.type === 'success' ? 'Store Initialized' : 'Store Initialization Issue'}
            >
              {storeFeedback.message}
            </Alert>
          )}

          {compactError && (
            <Alert variant="danger" title="Compaction Error">
              {compactError}
            </Alert>
          )}

          {compactResult && (
            <div>
              {compactResult.status === 'blocked' ? (
                <Alert variant="danger" title="Compaction Blocked (Safety Invariant Protected)">
                  Causal compaction was blocked by the safety boundary. Reason: <strong>{compactResult.reason}</strong>.
                  SemanticSync prevents compaction when unacknowledged operations exist or replica frontiers disagree.
                </Alert>
              ) : compactResult.status === 'retained' ? (
                <Alert variant="warning" title="Operations Retained (Safety Invariant Protected)">
                  No operations pruned: {compactResult.reason || 'Missing ACK from enrolled replicas'}. Full change logs remain intact.
                </Alert>
              ) : (
                <Alert variant="success" title="Causal Compaction Completed">
                  Successfully pruned <strong>{compactResult.pruned || 0}</strong> acknowledged operations across enrolled replicas.
                  {compactResult.stable_horizon && ` Causal horizon established at [${compactResult.stable_horizon.join(', ')}].`}
                </Alert>
              )}
            </div>
          )}

          {/* Blocked Checkpoints List if present */}
          {((syncStatus?.checkpoint_store?.blocked_checkpoints && syncStatus.checkpoint_store.blocked_checkpoints.length > 0) ||
            (compactResult?.blocked_checkpoints && compactResult.blocked_checkpoints.length > 0)) && (
            <div className="border border-danger/40 bg-rose-50/30 rounded-lg p-3">
              <div className="flex items-center gap-2 text-danger font-semibold text-xs mb-2">
                <AlertTriangle className="w-4 h-4" />
                <span>Blocked Checkpoint Records ({
                  (compactResult?.blocked_checkpoints || syncStatus?.checkpoint_store?.blocked_checkpoints).length
                })</span>
              </div>
              <p className="text-[11px] text-text-secondary mb-2">
                The following checkpoints could not be resumed or compacted due to precondition mismatches or missing causal dependencies:
              </p>
              <div className="space-y-2">
                {(compactResult?.blocked_checkpoints || syncStatus?.checkpoint_store?.blocked_checkpoints).map((b, idx) => (
                  <div key={idx} className="bg-white border border-border p-2.5 rounded text-xs font-mono">
                    <div className="flex justify-between items-center text-[11px] font-bold text-text-primary">
                      <span>Checkpoint ID: {b.checkpoint_id}</span>
                      <Badge variant="danger" size="sm">BLOCKED</Badge>
                    </div>
                    <div className="text-[11px] text-danger mt-1">Reason: {b.reason}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-border">
            <Button
              variant="outline"
              onClick={handleInitStore}
              loading={initializingStore}
              icon={ShieldCheck}
            >
              {syncStatus?.checkpoint_store?.status === 'ready'
                ? 'Revalidate / Adopt Checkpoint Store'
                : 'Initialize Checkpoint Store'}
            </Button>

            <Button
              variant="secondary"
              onClick={handleCompact}
              loading={compacting}
              disabled={!selectedDb || syncStatus?.checkpoint_store?.status === 'blocked'}
              icon={Layers}
            >
              Run Causal Compaction
            </Button>

            <span className="text-[11px] text-text-muted">
              Compaction safely snapshots state and truncates acknowledged operations up to the common ACK horizon.
            </span>
          </div>
        </div>
      </Card>
    </div>
  );
}
