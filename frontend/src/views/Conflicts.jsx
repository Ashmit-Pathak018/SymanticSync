import React, { useState, useEffect } from 'react';
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
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Alert } from '../components/ui/Alert';
import { api } from '../services/api';

export function Conflicts() {
  const { databases, refreshState } = useApp();

  const [conflicts, setConflicts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [dbFilter, setDbFilter] = useState('all');
  const [expandedId, setExpandedId] = useState(null);

  // Manual resolution custom value input map
  const [customValues, setCustomValues] = useState({});
  const [resolvingId, setResolvingId] = useState(null);
  const [resolveFeedback, setResolveFeedback] = useState(null);

  const loadConflicts = async () => {
    setLoading(true);
    try {
      const data = await api.getConflicts({
        status: statusFilter,
        db_id: dbFilter,
      });
      setConflicts(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load conflicts:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadConflicts();
  }, [statusFilter, dbFilter]);

  const handleResolve = async (conflictId, mode) => {
    setResolvingId(conflictId);
    setResolveFeedback(null);
    try {
      const customVal = customValues[conflictId] ?? null;
      const res = await api.resolveConflict(conflictId, mode, customVal);
      setResolveFeedback({
        id: conflictId,
        status: res.status,
        result: res.result,
        explanation: res.explanation,
      });
      await loadConflicts();
      await refreshState();
    } catch (err) {
      alert(`Resolution failed: ${err.message}`);
    } finally {
      setResolvingId(null);
    }
  };

  const pendingCount = conflicts.filter((c) => c.status === 'pending').length;
  const flaggedCount = conflicts.filter((c) => c.status === 'flagged').length;
  const resolvedCount = conflicts.filter((c) => c.status === 'resolved').length;

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Conflict Inspector & Resolver</h1>
          <p className="text-xs text-text-secondary mt-1">
            Three-way diff divergences detected across offline replicas. Review flagged records or execute deterministic semantic policies.
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
        <div className="flex items-center gap-3">
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
                className={`px-2.5 py-1 rounded text-xs capitalize transition-colors ${
                  statusFilter === st
                    ? 'bg-white text-text-primary font-semibold shadow-2xs'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                {st}
              </button>
            ))}
          </div>

          {/* Database Select */}
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

        <Button size="sm" variant="ghost" icon={RotateCcw} onClick={loadConflicts}>
          Refresh
        </Button>
      </div>

      {/* Conflicts List */}
      {loading ? (
        <div className="text-center py-16 text-text-muted text-xs">Loading conflicts...</div>
      ) : conflicts.length === 0 ? (
        <Card className="text-center py-12">
          <CheckCircle2 className="w-12 h-12 text-success mx-auto mb-3 opacity-90" />
          <h3 className="text-sm font-semibold text-text-primary">No Conflicts Matching Filter</h3>
          <p className="text-xs text-text-secondary max-w-md mx-auto mt-1 mb-4">
            All replicas are currently in sync, or no conflicts have been registered for this filter.
            You can inject simulated divergences from the Sync Hub.
          </p>
          <Button size="sm" variant="secondary" onClick={() => (window.location.href = '/sync')}>
            Go to Sync Hub
          </Button>
        </Card>
      ) : (
        <div className="space-y-3">
          {conflicts.map((c) => {
            const isExpanded = expandedId === c.conflict_id;
            const isResolving = resolvingId === c.conflict_id;

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
                    <button className="text-text-muted p-1 hover:text-text-primary">
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
                        Row #{c.row_id}
                      </span>
                      <span className="font-mono text-[10px] text-text-muted hidden sm:inline">
                        ID: {c.conflict_id.slice(0, 8)}...
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    {/* 3-way mini diff */}
                    <div className="hidden lg:flex items-center gap-2 text-xs font-mono bg-gray-50 border border-border/80 px-2.5 py-1 rounded-md">
                      <span className="text-text-muted">Base:</span>
                      <span className="font-semibold">{String(c.base_value)}</span>
                      <span className="text-text-muted">|</span>
                      <span className="text-primary font-medium">A: {String(c.value_a)}</span>
                      <span className="text-text-muted">vs</span>
                      <span className="text-primary font-medium">B: {String(c.value_b)}</span>
                    </div>

                    <Badge variant="policy" size="sm">
                      {c.policy}
                    </Badge>

                    <Badge variant={c.status} size="sm">
                      {c.status}
                    </Badge>
                  </div>
                </div>

                {/* Expanded Details & Resolution Panel */}
                {isExpanded && (
                  <div className="p-5 bg-gray-50/50 border-t border-border space-y-4">
                    {/* 3-Way Values Matrix */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs font-mono">
                      {/* Base State */}
                      <div className="bg-white p-3 rounded-lg border border-border">
                        <div className="text-[11px] font-sans font-semibold text-text-muted uppercase mb-1">
                          Common Base Value
                        </div>
                        <div className="text-sm font-bold text-text-primary truncate">
                          {c.base_value === null ? 'NULL' : String(c.base_value)}
                        </div>
                        <div className="text-[10px] font-sans text-text-muted mt-1">
                          Last known synchronized ancestor
                        </div>
                      </div>

                      {/* Replica A */}
                      <div className="bg-white p-3 rounded-lg border border-primary/30">
                        <div className="text-[11px] font-sans font-semibold text-primary uppercase mb-1 flex items-center justify-between">
                          <span>Replica A Edit</span>
                          <span className="text-[10px] lowercase font-mono">{c.replica_a_id}</span>
                        </div>
                        <div className="text-sm font-bold text-text-primary truncate">
                          {c.value_a === null ? 'NULL' : String(c.value_a)}
                        </div>
                        <div className="text-[10px] font-mono text-text-muted mt-1 truncate">
                          HLC: {c.replica_a_ts || 'N/A'}
                        </div>
                      </div>

                      {/* Replica B */}
                      <div className="bg-white p-3 rounded-lg border border-primary/30">
                        <div className="text-[11px] font-sans font-semibold text-primary uppercase mb-1 flex items-center justify-between">
                          <span>Replica B Edit</span>
                          <span className="text-[10px] lowercase font-mono">{c.replica_b_id}</span>
                        </div>
                        <div className="text-sm font-bold text-text-primary truncate">
                          {c.value_b === null ? 'NULL' : String(c.value_b)}
                        </div>
                        <div className="text-[10px] font-mono text-text-muted mt-1 truncate">
                          HLC: {c.replica_b_ts || 'N/A'}
                        </div>
                      </div>
                    </div>

                    {/* Resolution feedback banner if just resolved or explanation exists */}
                    {(c.explanation || (resolveFeedback && resolveFeedback.id === c.conflict_id)) && (
                      <div className="p-3 bg-white rounded-lg border border-success/30 text-xs">
                        <div className="flex items-center gap-1.5 text-success font-semibold">
                          <CheckCircle2 className="w-4 h-4" />
                          <span>Resolution Result</span>
                        </div>
                        <p className="mt-1 text-text-primary font-mono text-xs">
                          {resolveFeedback?.explanation || c.explanation || `Resolved value: ${c.resolved_value}`}
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
                        {/* 1. Auto-resolve with Policy */}
                        <Button
                          size="sm"
                          variant="primary"
                          loading={isResolving}
                          onClick={() => handleResolve(c.conflict_id, 'auto')}
                          title={`Auto-resolve using ${c.policy} merge policy`}
                        >
                          Auto Resolve ({c.policy})
                        </Button>

                        {/* 2. Pick A */}
                        <Button
                          size="sm"
                          variant="secondary"
                          loading={isResolving}
                          onClick={() => handleResolve(c.conflict_id, 'pick_a')}
                          title="Adopt Replica A value"
                        >
                          Pick Replica A ({String(c.value_a)})
                        </Button>

                        {/* 3. Pick B */}
                        <Button
                          size="sm"
                          variant="secondary"
                          loading={isResolving}
                          onClick={() => handleResolve(c.conflict_id, 'pick_b')}
                          title="Adopt Replica B value"
                        >
                          Pick Replica B ({String(c.value_b)})
                        </Button>

                        {/* 4. Custom Value Input */}
                        <div className="flex items-center gap-1.5 ml-auto">
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
