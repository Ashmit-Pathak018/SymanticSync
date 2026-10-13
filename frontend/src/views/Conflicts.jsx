import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Zap,
  Filter,
  CheckCircle2,
  AlertTriangle,
  Clock,
  RotateCcw,
  Sparkles,
  ChevronDown,
  ChevronRight,
  ShieldCheck,
  Check,
  ArrowRight,
  Info,
  Layers,
  Copy,
  ExternalLink,
  ShieldAlert,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Alert } from '../components/ui/Alert';
import { api } from '../services/api';

export function Conflicts() {
  const { databases, selectedDbId, refreshState, refreshCounter } = useApp();

  const [conflicts, setConflicts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [dbFilter, setDbFilter] = useState(selectedDbId || 'all');
  const [expandedId, setExpandedId] = useState(null);

  // Manual resolution custom value input map (scalar or JSON string)
  const [customValues, setCustomValues] = useState({});
  const [resolvingId, setResolvingId] = useState(null);
  const [resolveFeedback, setResolveFeedback] = useState(null);
  const [resolveError, setResolveError] = useState(null);

  const requestIdRef = useRef(0);

  // Sync dbFilter when active workspace changes
  useEffect(() => {
    if (selectedDbId) {
      setDbFilter(selectedDbId);
    }
  }, [selectedDbId]);

  const loadConflicts = useCallback(async () => {
    const reqId = ++requestIdRef.current;
    setLoading(true);
    setResolveError(null);
    try {
      const data = await api.getConflicts({
        status: statusFilter,
        db_id: dbFilter,
      });
      if (reqId !== requestIdRef.current) return;
      const list = Array.isArray(data) ? data : [];
      setConflicts(list);
    } catch (err) {
      if (reqId === requestIdRef.current) {
        console.error('Failed to load conflicts:', err);
      }
    } finally {
      if (reqId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [statusFilter, dbFilter]);

  useEffect(() => {
    loadConflicts();
  }, [loadConflicts, refreshCounter]);

  const handleResolve = async (conflictId, mode) => {
    setResolvingId(conflictId);
    setResolveFeedback(null);
    setResolveError(null);

    const c = conflicts.find((item) => item.conflict_id === conflictId);
    let customVal = customValues[conflictId] ?? null;

    // For INSERT collisions, custom value must be a valid complete JSON object
    if (mode === 'custom' && c && (c.conflict_type === 'INSERT_INSERT' || c.conflict_type === 'UNIQUE_COLLISION')) {
      try {
        if (typeof customVal === 'string') {
          customVal = JSON.parse(customVal);
        }
        if (!customVal || typeof customVal !== 'object' || Array.isArray(customVal)) {
          throw new Error('Custom payload for insert collisions must be a valid JSON object dictionary.');
        }
      } catch (parseErr) {
        setResolveError({
          id: conflictId,
          message: `Invalid JSON payload: ${parseErr.message}`,
        });
        setResolvingId(null);
        return;
      }
    }

    try {
      const res = await api.resolveConflict(conflictId, mode, customVal);

      if (res && res.status === 'resolved') {
        setResolveFeedback({
          id: conflictId,
          status: res.status,
          result: res.result,
          explanation: res.explanation,
        });
        await loadConflicts();
        await refreshState();
      } else {
        throw new Error(res?.explanation || 'Backend did not confirm successful resolution.');
      }
    } catch (err) {
      setResolveError({
        id: conflictId,
        message: err.data?.detail || err.message,
      });
    } finally {
      setResolvingId(null);
    }
  };

  const filteredConflicts = conflicts.filter((c) => {
    if (typeFilter !== 'all' && (c.conflict_type || 'UPDATE_UPDATE') !== typeFilter) {
      return false;
    }
    return true;
  });

  const pendingCount = conflicts.filter((c) => c.status === 'pending').length;
  const flaggedCount = conflicts.filter((c) => c.status === 'flagged').length;
  const resolvedCount = conflicts.filter((c) => c.status === 'resolved').length;

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-primary bg-primary-light px-2 py-0.5 rounded-sm font-semibold">
              Deterministic Convergence
            </span>
            <span className="text-xs text-text-muted">/</span>
            <span className="text-xs font-semibold text-text-secondary">Full Mutation Model</span>
          </div>
          <h1 className="text-xl font-bold text-text-primary mt-1">
            Conflict Inspector & Semantic Resolver
          </h1>
          <p className="text-xs text-text-secondary mt-0.5">
            Evaluates concurrent update divergences, primary-key insert collisions, tombstones, and bounded invariant limits.
          </p>
        </div>

        {/* Counter Pills */}
        <div className="flex items-center gap-2">
          <Badge variant="pending" size="md">
            {pendingCount} Pending
          </Badge>
          <Badge variant="flagged" size="md">
            {flaggedCount} Flagged
          </Badge>
          <Badge variant="resolved" size="md">
            {resolvedCount} Resolved
          </Badge>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="bg-white border border-border rounded-lg p-3.5 flex flex-wrap items-center justify-between gap-3 shadow-xs text-xs">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5 text-text-secondary font-semibold uppercase tracking-wider text-[11px]">
            <Filter className="w-3.5 h-3.5 text-primary" />
            <span>Filter:</span>
          </div>

          {/* Status Buttons */}
          <div className="flex items-center gap-1 bg-gray-100 p-0.5 rounded-md">
            {['all', 'pending', 'flagged', 'resolved'].map((st) => (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                className={`px-2.5 py-1 rounded text-xs capitalize transition-colors cursor-pointer ${
                  statusFilter === st
                    ? 'bg-white text-text-primary font-semibold shadow-2xs'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                {st}
              </button>
            ))}
          </div>

          {/* Conflict Type Filter */}
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="text-xs bg-gray-50 border border-border rounded-md px-2.5 py-1 text-text-primary focus:ring-1 focus:ring-primary focus:outline-hidden"
          >
            <option value="all">All Conflict Types</option>
            <option value="UPDATE_UPDATE">Update Divergence (UPDATE vs UPDATE)</option>
            <option value="INSERT_INSERT">Insert Collision (INSERT vs INSERT PK)</option>
            <option value="UNIQUE_COLLISION">Unique Key Collision (Secondary UNIQUE)</option>
            <option value="UPDATE_DELETE">Tombstone (UPDATE vs DELETE)</option>
            <option value="DELETE_DELETE">Concurrent Delete (DELETE vs DELETE)</option>
          </select>

          {/* Workspace Select */}
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
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            icon={ShieldAlert}
            onClick={() => (window.location.href = '/quarantine')}
            title="Inspect orphaned records held in foreign-key quarantine"
          >
            Quarantine Store
          </Button>
          <Button size="sm" variant="ghost" icon={RotateCcw} onClick={loadConflicts}>
            Refresh
          </Button>
        </div>
      </div>

      {/* Conflicts List */}
      {loading ? (
        <div className="text-center py-16 text-text-muted text-xs">Loading conflicts...</div>
      ) : filteredConflicts.length === 0 ? (
        <Card className="text-center py-12">
          <CheckCircle2 className="w-12 h-12 text-success mx-auto mb-3 opacity-90" />
          <h3 className="text-sm font-semibold text-text-primary">No Conflicts Matching Filter</h3>
          <p className="text-xs text-text-secondary max-w-md mx-auto mt-1 mb-4">
            All replicas are currently converged, or no conflicts match the active status/type criteria.
            You can inject controlled divergences from the Sync Hub.
          </p>
          <Button size="sm" variant="secondary" onClick={() => (window.location.href = '/sync')}>
            Go to CRDT Sync Hub
          </Button>
        </Card>
      ) : (
        <div className="space-y-3">
          {filteredConflicts.map((c) => {
            const isExpanded = expandedId === c.conflict_id;
            const isResolving = resolvingId === c.conflict_id;
            const isInsertCollision =
              c.conflict_type === 'INSERT_INSERT' || c.conflict_type === 'UNIQUE_COLLISION';
            const isTombstone = c.conflict_type === 'UPDATE_DELETE';
            const isBounded = String(c.policy || '').startsWith('BOUNDED_SUM');

            const feedback =
              resolveFeedback && resolveFeedback.id === c.conflict_id ? resolveFeedback : null;
            const errFeedback =
              resolveError && resolveError.id === c.conflict_id ? resolveError : null;

            return (
              <div
                key={c.conflict_id}
                className={`bg-white border rounded-xl overflow-hidden transition-all shadow-xs ${
                  c.status === 'flagged'
                    ? 'border-danger/40'
                    : c.status === 'resolved'
                    ? 'border-success/30'
                    : 'border-border'
                }`}
              >
                {/* Accordion Header */}
                <div
                  onClick={() => setExpandedId(isExpanded ? null : c.conflict_id)}
                  className="p-4 hover:bg-gray-50/70 cursor-pointer flex flex-col md:flex-row md:items-center justify-between gap-3 select-none"
                >
                  <div className="flex items-center gap-3">
                    <button className="text-text-muted p-1 hover:text-text-primary cursor-pointer">
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4" />
                      ) : (
                        <ChevronRight className="w-4 h-4" />
                      )}
                    </button>

                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-bold text-text-primary">
                        {c.table}.{c.column}
                      </span>
                      <span className="font-mono text-xs text-text-muted bg-gray-100 px-1.5 py-0.5 rounded-sm">
                        Row #{String(c.row_id)}
                      </span>
                      <span className="font-mono text-[10px] text-text-muted hidden sm:inline">
                        ID: {c.conflict_id.slice(0, 8)}...
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2.5">
                    {/* Conflict Type Pill */}
                    <span
                      className={`text-[10px] font-mono px-2 py-0.5 rounded-sm font-semibold border ${
                        isInsertCollision
                          ? 'bg-amber-50 text-amber-800 border-amber-300'
                          : isTombstone
                          ? 'bg-purple-50 text-purple-800 border-purple-300'
                          : 'bg-blue-50 text-blue-800 border-blue-200'
                      }`}
                    >
                      {c.conflict_type || 'UPDATE_UPDATE'}
                    </span>

                    {/* Policy Badge */}
                    <Badge variant="policy" size="sm">
                      {c.policy}
                    </Badge>

                    {/* Status Badge */}
                    <Badge variant={c.status} size="sm">
                      {c.status}
                    </Badge>
                  </div>
                </div>

                {/* Expanded Details & Resolution Panel */}
                {isExpanded && (
                  <div className="p-5 bg-gray-50/50 border-t border-border space-y-4">
                    {/* Inline Error Alert */}
                    {errFeedback && (
                      <Alert variant="danger" title="Conflict Resolution Error">
                        {errFeedback.message}
                      </Alert>
                    )}

                    {/* Context Explanation */}
                    {c.explanation && (
                      <div className="p-3 bg-white rounded-lg border border-border text-xs flex items-start gap-2">
                        <Info className="w-4 h-4 text-primary flex-shrink-0 mt-0.5" />
                        <div>
                          <span className="font-semibold text-text-primary">Conflict Context: </span>
                          <span className="text-text-secondary font-mono">{c.explanation}</span>
                        </div>
                      </div>
                    )}

                    {/* 3-Way Values Matrix */}
                    {isInsertCollision ? (
                      /* INSERT Collision View: Full Payloads */
                      <div className="space-y-3">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
                          {/* Replica A Payload */}
                          <div className="bg-white p-3.5 rounded-lg border border-primary/30">
                            <div className="text-[11px] font-sans font-semibold text-primary uppercase mb-1.5 flex items-center justify-between">
                              <span>Replica A Complete Row</span>
                              <span className="text-[10px] lowercase">{c.replica_a_id}</span>
                            </div>
                            <pre className="p-2.5 bg-gray-50 rounded-md text-[11px] overflow-x-auto max-h-40 text-text-primary">
                              {typeof c.value_a === 'object'
                                ? JSON.stringify(c.value_a, null, 2)
                                : String(c.value_a)}
                            </pre>
                            <div className="text-[10px] font-mono text-text-muted mt-1 truncate">
                              HLC: {c.replica_a_ts || 'N/A'}
                            </div>
                          </div>

                          {/* Replica B Payload */}
                          <div className="bg-white p-3.5 rounded-lg border border-primary/30">
                            <div className="text-[11px] font-sans font-semibold text-primary uppercase mb-1.5 flex items-center justify-between">
                              <span>Replica B Complete Row</span>
                              <span className="text-[10px] lowercase">{c.replica_b_id}</span>
                            </div>
                            <pre className="p-2.5 bg-gray-50 rounded-md text-[11px] overflow-x-auto max-h-40 text-text-primary">
                              {typeof c.value_b === 'object'
                                ? JSON.stringify(c.value_b, null, 2)
                                : String(c.value_b)}
                            </pre>
                            <div className="text-[10px] font-mono text-text-muted mt-1 truncate">
                              HLC: {c.replica_b_ts || 'N/A'}
                            </div>
                          </div>
                        </div>

                        <div className="p-2.5 bg-amber-50 border border-amber-200 rounded-md text-amber-900 text-xs flex items-center gap-2">
                          <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
                          <span>
                            <strong>Insert Collision Policy Boundary:</strong> Automatic merge is not allowed for insert collisions.
                            You must explicitly choose either Replica A, Replica B, or provide a complete replacement payload dictionary.
                          </span>
                        </div>
                      </div>
                    ) : (
                      /* Cell-Level 3-Way Diff Matrix */
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs font-mono">
                        {/* Common Base State */}
                        <div className="bg-white p-3 rounded-lg border border-border">
                          <div className="text-[11px] font-sans font-semibold text-text-muted uppercase mb-1">
                            Common Base Value
                          </div>
                          <div className="text-sm font-bold text-text-primary truncate">
                            {c.base_value === null ? 'NULL' : String(c.base_value)}
                          </div>
                          <div className="text-[10px] font-sans text-text-muted mt-1">
                            Synchronized ancestor state
                          </div>
                        </div>

                        {/* Replica A */}
                        <div className="bg-white p-3 rounded-lg border border-primary/30">
                          <div className="text-[11px] font-sans font-semibold text-primary uppercase mb-1 flex items-center justify-between">
                            <span>Replica A Value</span>
                            <span className="text-[10px] lowercase">{c.replica_a_id}</span>
                          </div>
                          <div className="text-sm font-bold text-text-primary truncate">
                            {c.value_a === null ? 'NULL (Deleted)' : String(c.value_a)}
                          </div>
                          <div className="text-[10px] font-mono text-text-muted mt-1 truncate">
                            HLC: {c.replica_a_ts || 'N/A'}
                          </div>
                        </div>

                        {/* Replica B */}
                        <div className="bg-white p-3 rounded-lg border border-primary/30">
                          <div className="text-[11px] font-sans font-semibold text-primary uppercase mb-1 flex items-center justify-between">
                            <span>Replica B Value</span>
                            <span className="text-[10px] lowercase">{c.replica_b_id}</span>
                          </div>
                          <div className="text-sm font-bold text-text-primary truncate">
                            {c.value_b === null ? 'NULL (Deleted)' : String(c.value_b)}
                          </div>
                          <div className="text-[10px] font-mono text-text-muted mt-1 truncate">
                            HLC: {c.replica_b_ts || 'N/A'}
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Resolution Result Banner */}
                    {(feedback || (c.status === 'resolved' && c.resolved_value !== undefined)) && (
                      <div className="p-3 bg-white rounded-lg border border-success/30 text-xs">
                        <div className="flex items-center gap-1.5 text-success font-semibold">
                          <CheckCircle2 className="w-4 h-4" />
                          <span>Resolution Confirmed & Persisted in SQLite</span>
                        </div>
                        <p className="mt-1 text-text-primary font-mono text-xs">
                          {feedback?.explanation ||
                            c.explanation ||
                            `Resolved value: ${
                              typeof c.resolved_value === 'object'
                                ? JSON.stringify(c.resolved_value)
                                : String(c.resolved_value)
                            }`}
                        </p>
                      </div>
                    )}

                    {/* Resolution Actions Bar */}
                    <div className="bg-white p-4 rounded-lg border border-border">
                      <div className="text-xs font-semibold text-text-primary mb-2 flex items-center gap-1.5">
                        <ShieldCheck className="w-4 h-4 text-primary" />
                        <span>Resolution Actions:</span>
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        {/* 1. Auto-resolve with Policy (Disabled for insert collisions) */}
                        {!isInsertCollision && (
                          <Button
                            size="sm"
                            variant="primary"
                            loading={isResolving}
                            onClick={() => handleResolve(c.conflict_id, 'auto')}
                            title={`Execute ${c.policy} merge resolver`}
                          >
                            Auto Resolve ({c.policy})
                          </Button>
                        )}

                        {/* 2. Pick A */}
                        <Button
                          size="sm"
                          variant="secondary"
                          loading={isResolving}
                          onClick={() => handleResolve(c.conflict_id, 'pick_a')}
                          title="Adopt Replica A value atomically across both replicas"
                        >
                          Pick Replica A {isInsertCollision ? 'Payload' : `(${String(c.value_a)})`}
                        </Button>

                        {/* 3. Pick B */}
                        <Button
                          size="sm"
                          variant="secondary"
                          loading={isResolving}
                          onClick={() => handleResolve(c.conflict_id, 'pick_b')}
                          title="Adopt Replica B value atomically across both replicas"
                        >
                          Pick Replica B {isInsertCollision ? 'Payload' : `(${String(c.value_b)})`}
                        </Button>

                        {/* 4. Custom Value Input */}
                        <div className="flex items-center gap-1.5 ml-auto">
                          {isInsertCollision ? (
                            <div className="flex items-center gap-2">
                              <input
                                type="text"
                                placeholder='{"id": 1, ...}'
                                value={customValues[c.conflict_id] || ''}
                                onChange={(e) =>
                                  setCustomValues({
                                    ...customValues,
                                    [c.conflict_id]: e.target.value,
                                  })
                                }
                                className="text-xs font-mono border border-border rounded-md px-2.5 py-1.5 w-48 text-text-primary focus:ring-1 focus:ring-primary focus:outline-hidden"
                              />
                              <Button
                                size="sm"
                                variant="outline"
                                loading={isResolving}
                                onClick={() => handleResolve(c.conflict_id, 'custom')}
                                title="Apply complete replacement dictionary"
                              >
                                Replace Row
                              </Button>
                            </div>
                          ) : (
                            <div className="flex items-center gap-1.5">
                              <input
                                type="text"
                                placeholder="Custom value..."
                                value={customValues[c.conflict_id] || ''}
                                onChange={(e) =>
                                  setCustomValues({
                                    ...customValues,
                                    [c.conflict_id]: e.target.value,
                                  })
                                }
                                className="text-xs font-mono border border-border rounded-md px-2.5 py-1.5 w-36 text-text-primary focus:ring-1 focus:ring-primary focus:outline-hidden"
                              />
                              <Button
                                size="sm"
                                variant="outline"
                                loading={isResolving}
                                onClick={() => handleResolve(c.conflict_id, 'custom')}
                              >
                                Apply Custom
                              </Button>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
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
