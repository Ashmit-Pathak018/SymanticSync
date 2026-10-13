import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  RotateCcw,
  Trash2,
  Link2,
  CheckCircle2,
  AlertTriangle,
  Info,
  Filter,
  Search,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  Database,
  Layers,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Alert } from '../components/ui/Alert';
import { api } from '../services/api';

export function Quarantine() {
  const { databases, selectedDbId, refreshCounter, refreshState } = useApp();

  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [dbFilter, setDbFilter] = useState(selectedDbId || 'all');
  const [tableFilter, setTableFilter] = useState('');
  const [expandedId, setExpandedId] = useState(null);

  // Relink action inputs: quarantineId -> parentId
  const [relinkInputs, setRelinkInputs] = useState({});
  const [actionLoadingId, setActionLoadingId] = useState(null);
  const [actionFeedback, setActionFeedback] = useState(null);

  const requestIdRef = useRef(0);

  useEffect(() => {
    if (selectedDbId) {
      setDbFilter(selectedDbId);
    }
  }, [selectedDbId]);

  const loadQuarantine = useCallback(async () => {
    const reqId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const data = await api.listQuarantine({
        status: statusFilter,
        db_id: dbFilter,
        table: tableFilter.trim() || undefined,
      });
      if (reqId !== requestIdRef.current) return;
      setRecords(Array.isArray(data) ? data : []);
    } catch (err) {
      if (reqId === requestIdRef.current) {
        console.error('Failed to load quarantine records:', err);
        setError(err.data?.detail || err.message);
      }
    } finally {
      if (reqId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [statusFilter, dbFilter, tableFilter]);

  useEffect(() => {
    loadQuarantine();
  }, [loadQuarantine, refreshCounter]);

  const handleResolve = async (quarantineId, action, newParentId = null) => {
    setActionLoadingId(quarantineId);
    setActionFeedback(null);
    try {
      const dbIdParam = dbFilter !== 'all' ? dbFilter : selectedDbId;
      const res = await api.resolveQuarantine(
        quarantineId,
        action,
        newParentId,
        dbIdParam
      );

      // Verify that backend actually marked it as resolved
      if (res && (res.status === action || res.status === 'confirmed_deleted' || res.status === 'relinked')) {
        setActionFeedback({
          id: quarantineId,
          type: 'success',
          message:
            action === 'confirmed_deleted'
              ? `Record '${quarantineId.slice(0, 8)}' confirmed deleted and archived.`
              : `Record '${quarantineId.slice(0, 8)}' successfully relinked under parent #${newParentId}.`,
        });
        await loadQuarantine();
        await refreshState();
      } else {
        throw new Error('Backend did not return confirmation of resolution.');
      }
    } catch (err) {
      setActionFeedback({
        id: quarantineId,
        type: 'error',
        message: err.data?.detail || err.message,
      });
    } finally {
      setActionLoadingId(null);
    }
  };

  const quarantinedCount = records.filter((r) => r.status === 'quarantined').length;
  const relinkedCount = records.filter((r) => r.status === 'relinked').length;
  const deletedCount = records.filter((r) => r.status === 'confirmed_deleted').length;

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-primary bg-primary-light px-2 py-0.5 rounded-sm font-semibold">
              Relational Invariants
            </span>
            <span className="text-xs text-text-muted">/</span>
            <span className="text-xs font-semibold text-text-secondary">Foreign Key Isolation</span>
          </div>
          <h1 className="text-xl font-bold text-text-primary mt-1">
            Quarantine Management
          </h1>
          <p className="text-xs text-text-secondary mt-0.5">
            Atomically isolated orphaned child records whose parent rows were removed or divergent during synchronization.
          </p>
        </div>

        {/* Status Counters */}
        <div className="flex items-center gap-2">
          <Badge variant="flagged" size="md">
            {quarantinedCount} Quarantined
          </Badge>
          <Badge variant="resolved" size="md">
            {relinkedCount} Relinked
          </Badge>
          <Badge variant="neutral" size="md">
            {deletedCount} Confirmed Deleted
          </Badge>
        </div>
      </div>

      {/* Scientific Invariant Info Banner */}
      <Alert variant="info" title="Relational Integrity & Foreign Key Isolation Boundary">
        SemanticSync enforces <code className="font-mono font-bold">PRAGMA foreign_keys = ON</code> before all write transactions.
        When a parent entity is deleted across replicas, orphaned child payloads are atomically moved to quarantine in the same transaction
        before parent mutation commits. Quarantined records can be safely relinked under an existing parent or confirmed deleted for audit retention.
      </Alert>

      {/* Filter Toolbar */}
      <div className="bg-white border border-border rounded-lg p-3.5 flex flex-wrap items-center justify-between gap-3 shadow-xs text-xs">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5 text-text-secondary font-semibold uppercase tracking-wider text-[11px]">
            <Filter className="w-3.5 h-3.5 text-primary" />
            <span>Filter:</span>
          </div>

          {/* Status Tabs */}
          <div className="flex items-center gap-1 bg-gray-100 p-0.5 rounded-md">
            {[
              { id: 'all', label: 'All' },
              { id: 'quarantined', label: 'Quarantined' },
              { id: 'relinked', label: 'Relinked' },
              { id: 'confirmed_deleted', label: 'Deleted' },
            ].map((st) => (
              <button
                key={st.id}
                onClick={() => setStatusFilter(st.id)}
                className={`px-2.5 py-1 rounded text-xs capitalize transition-colors cursor-pointer ${
                  statusFilter === st.id
                    ? 'bg-white text-text-primary font-semibold shadow-2xs'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                {st.label}
              </button>
            ))}
          </div>

          {/* Workspace Filter */}
          <select
            value={dbFilter}
            onChange={(e) => setDbFilter(e.target.value)}
            className="text-xs bg-gray-50 border border-border rounded-md px-2.5 py-1 text-text-primary focus:ring-1 focus:ring-primary focus:outline-hidden"
          >
            <option value="all">All Workspaces</option>
            {databases.map((db) => (
              <option key={db.id} value={db.id}>
                {db.name}
              </option>
            ))}
          </select>

          {/* Table Search Input */}
          <div className="flex items-center gap-1 border border-border bg-gray-50 rounded-md px-2 py-0.5">
            <Search className="w-3 h-3 text-text-muted" />
            <input
              type="text"
              placeholder="Filter by table..."
              value={tableFilter}
              onChange={(e) => setTableFilter(e.target.value)}
              className="text-xs bg-transparent border-none text-text-primary focus:outline-hidden w-28"
            />
          </div>
        </div>

        <Button size="sm" variant="ghost" icon={RotateCcw} onClick={loadQuarantine}>
          Refresh
        </Button>
      </div>

      {/* Global Error Banner if list fails */}
      {error && (
        <Alert variant="danger" title="Failed to Load Quarantine Store">
          {error}
        </Alert>
      )}

      {/* Records List */}
      {loading ? (
        <div className="text-center py-16 text-text-muted text-xs">
          Loading quarantined records from SQLite store...
        </div>
      ) : records.length === 0 ? (
        <Card className="text-center py-12">
          <ShieldCheck className="w-12 h-12 text-success mx-auto mb-3 opacity-90" />
          <h3 className="text-sm font-semibold text-text-primary">No Quarantined Records Found</h3>
          <p className="text-xs text-text-secondary max-w-md mx-auto mt-1 mb-4">
            Foreign key invariants are fully satisfied across all synchronized tables. Zero orphaned records are held in quarantine.
          </p>
          <Button size="sm" variant="secondary" onClick={() => (window.location.href = '/conflicts')}>
            View Active Conflicts
          </Button>
        </Card>
      ) : (
        <div className="space-y-3">
          {records.map((r) => {
            const isExpanded = expandedId === r.quarantine_id;
            const isActionLoading = actionLoadingId === r.quarantine_id;
            const feedback = actionFeedback && actionFeedback.id === r.quarantine_id ? actionFeedback : null;

            let parsedPayload = null;
            const rawPayload = r.row_payload ?? r.payload;
            try {
              parsedPayload = typeof rawPayload === 'string' ? JSON.parse(rawPayload) : rawPayload;
            } catch {
              parsedPayload = rawPayload;
            }

            return (
              <div
                key={r.quarantine_id}
                className={`bg-white border rounded-xl overflow-hidden transition-all shadow-xs ${
                  r.status === 'quarantined'
                    ? 'border-warning/50'
                    : r.status === 'relinked'
                    ? 'border-success/40'
                    : 'border-border'
                }`}
              >
                {/* Header Row */}
                <div
                  onClick={() => setExpandedId(isExpanded ? null : r.quarantine_id)}
                  className="p-4 hover:bg-gray-50/70 cursor-pointer flex flex-col md:flex-row md:items-center justify-between gap-3 select-none"
                >
                  <div className="flex items-center gap-3">
                    <button className="text-text-muted p-1 hover:text-text-primary cursor-pointer">
                      {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                    </button>

                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-bold text-text-primary">
                        {r.table_name}
                      </span>
                      <span className="font-mono text-xs text-text-muted bg-gray-100 px-1.5 py-0.5 rounded-sm">
                        Row #{String(r.row_id)}
                      </span>
                      <span className="font-mono text-[10px] text-text-muted hidden sm:inline">
                        ID: {r.quarantine_id.slice(0, 8)}...
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <span className="text-xs text-text-secondary truncate max-w-xs font-mono">
                      Reason: {r.reason || 'Parent key missing'}
                    </span>

                    <Badge
                      variant={
                        r.status === 'quarantined'
                          ? 'flagged'
                          : r.status === 'relinked'
                          ? 'resolved'
                          : 'neutral'
                      }
                      size="sm"
                    >
                      {r.status}
                    </Badge>
                  </div>
                </div>

                {/* Expanded Details and Resolution Form */}
                {isExpanded && (
                  <div className="p-5 bg-gray-50/50 border-t border-border space-y-4 text-xs">
                    {/* Action Feedback Banner */}
                    {feedback && (
                      <Alert
                        variant={feedback.type === 'success' ? 'success' : 'danger'}
                        title={feedback.type === 'success' ? 'Quarantine Action Completed' : 'Action Validation Failed'}
                      >
                        {feedback.message}
                      </Alert>
                    )}

                    {/* Metadata & Timestamp Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 font-mono">
                      <div className="bg-white p-3 rounded-lg border border-border">
                        <div className="text-[11px] font-sans font-semibold text-text-muted uppercase mb-1">
                          Source Table & Key
                        </div>
                        <div className="text-sm font-bold text-text-primary">
                          {r.table_name} #{String(r.row_id)}
                        </div>
                        <div className="text-[10px] text-text-muted mt-0.5 font-sans">
                          Foreign Key dependency violation
                        </div>
                      </div>

                      <div className="bg-white p-3 rounded-lg border border-border">
                        <div className="text-[11px] font-sans font-semibold text-text-muted uppercase mb-1">
                          Isolation Reason
                        </div>
                        <div className="text-xs font-semibold text-danger truncate">
                          {r.reason || 'Referenced parent record deleted'}
                        </div>
                        <div className="text-[10px] text-text-muted mt-0.5 font-sans">
                          Preserved to prevent cascade corruption
                        </div>
                      </div>

                      <div className="bg-white p-3 rounded-lg border border-border">
                        <div className="text-[11px] font-sans font-semibold text-text-muted uppercase mb-1">
                          Timestamp
                        </div>
                        <div className="text-xs font-semibold text-text-primary truncate">
                          {r.quarantined_at || 'Recorded at sync'}
                        </div>
                        <div className="text-[10px] text-text-muted mt-0.5 font-sans">
                          Audit trail persisted in SQLite
                        </div>
                      </div>
                    </div>

                    {/* Preserved Row Payload Card */}
                    <div className="bg-white p-4 rounded-lg border border-border">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-semibold text-text-primary flex items-center gap-1.5 font-sans">
                          <Layers className="w-4 h-4 text-primary" />
                          <span>Complete Preserved Row Payload:</span>
                        </span>
                        <span className="text-[11px] text-text-muted font-mono">JSON Snapshot</span>
                      </div>
                      <pre className="p-3 bg-gray-900 text-gray-100 rounded-md font-mono text-[11px] overflow-x-auto max-h-48">
                        {JSON.stringify(parsedPayload, null, 2)}
                      </pre>
                    </div>

                    {/* Resolution Controls for Active Quarantined Records */}
                    {r.status === 'quarantined' ? (
                      <div className="bg-white p-4 rounded-lg border border-border">
                        <div className="text-xs font-semibold text-text-primary mb-3 flex items-center gap-1.5 font-sans">
                          <ShieldCheck className="w-4 h-4 text-primary" />
                          <span>Recovery Actions:</span>
                        </div>

                        <div className="flex flex-wrap items-center gap-3">
                          {/* Option 1: Confirm Deletion */}
                          <Button
                            size="sm"
                            variant="secondary"
                            icon={Trash2}
                            loading={isActionLoading}
                            onClick={() => handleResolve(r.quarantine_id, 'confirmed_deleted')}
                            title="Confirm parent deletion was intentional and child can be safely archived"
                          >
                            Confirm Deletion (Archive)
                          </Button>

                          {/* Option 2: Relink under new parent */}
                          <div className="flex items-center gap-2 ml-auto">
                            <span className="text-xs text-text-secondary font-sans font-medium">
                              New Parent ID:
                            </span>
                            <input
                              type="text"
                              placeholder="e.g. 2"
                              value={relinkInputs[r.quarantine_id] || ''}
                              onChange={(e) =>
                                setRelinkInputs({
                                  ...relinkInputs,
                                  [r.quarantine_id]: e.target.value,
                                cloth: true,
                                })
                              }
                              className="text-xs font-mono border border-border rounded-md px-2.5 py-1.5 w-24 text-text-primary focus:ring-1 focus:ring-primary focus:outline-hidden"
                            />
                            <Button
                              size="sm"
                              variant="primary"
                              icon={Link2}
                              loading={isActionLoading}
                              disabled={!relinkInputs[r.quarantine_id]?.trim()}
                              onClick={() =>
                                handleResolve(
                                  r.quarantine_id,
                                  'relinked',
                                  relinkInputs[r.quarantine_id]?.trim()
                                )
                              }
                              title="Re-insert child row under verified parent ID in an atomic transaction"
                            >
                              Relink Parent & Restore
                            </Button>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="p-3 bg-gray-100 rounded-lg text-text-secondary flex items-center gap-2">
                        <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0" />
                        <span>
                          This record has been resolved as{' '}
                          <strong className="text-text-primary font-mono">{r.status}</strong>.
                          {r.new_parent_row_id && ` Relinked to Parent ID: ${r.new_parent_row_id}.`}
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
