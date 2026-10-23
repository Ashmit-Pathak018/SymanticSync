import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Database,
  GitBranch,
  Zap,
  RefreshCw,
  Layers,
  Terminal,
  ShieldCheck,
  Cpu,
  ArrowRight,
  CheckCircle2,
  Plus,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Alert } from '../components/ui/Alert';
import { api } from '../services/api';

export function Dashboard() {
  const { databases, syncStatus, setSelectedDbId, refreshCounter } = useApp();
  const navigate = useNavigate();

  const [conflicts, setConflicts] = useState([]);
  const [conflictError, setConflictError] = useState(null);
  const [loadingConflicts, setLoadingConflicts] = useState(false);

  useEffect(() => {
    async function loadRecentConflicts() {
      setLoadingConflicts(true);
      try {
        const list = await api.getConflicts();
        setConflicts(Array.isArray(list) ? list.slice(0, 5) : []);
        setConflictError(null);
      } catch (err) {
        setConflicts([]);
        setConflictError(err.message || 'Conflict activity is unavailable.');
        console.error('Failed to load conflicts:', err);
      } finally {
        setLoadingConflicts(false);
      }
    }
    loadRecentConflicts();
  }, [refreshCounter]);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Top Welcome & Mission Banner */}
      <div className="bg-gradient-to-r from-nav via-[#18234D] to-[#111A3A] text-white rounded-xl p-6 md:p-8 shadow-sm border border-white/10 relative overflow-hidden">
        <div className="max-w-3xl relative z-10">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/25 border border-primary/40 text-primary-light text-xs font-semibold mb-3">
            <Cpu className="w-3.5 h-3.5" />
            <span>Local-First Relational Sync Middleware</span>
          </div>
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-white mb-2">
            SemanticSync Studio
          </h1>
          <p className="text-sm md:text-base text-gray-300 leading-relaxed">
            SemanticSync explores schema-level policies for resolving tracked changes in SQLite replicas. Convergence and application-level correctness are separate questions; results depend on the policy, operation history, and tested schedule.
          </p>

          <div className="flex flex-wrap items-center gap-3 mt-5">
            <Button
              variant="primary"
              icon={Database}
              onClick={() => navigate('/databases')}
            >
              Browse Workspaces
            </Button>
            <Button
              variant="outline"
              className="bg-white/10 text-white border-white/20 hover:bg-white/20"
              icon={RefreshCw}
              onClick={() => navigate('/sync')}
            >
              Run Replica Sync Pipeline
            </Button>
          </div>
        </div>

        {/* Decorative Grid SVG in background */}
        <div className="absolute right-0 top-0 bottom-0 w-1/3 opacity-10 pointer-events-none flex items-center justify-center">
          <RefreshCw className="w-64 h-64 text-white" />
        </div>
      </div>

      {/* Core Architecture Pillars */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-lg border border-border flex items-start gap-3 shadow-xs">
          <div className="p-2.5 rounded-md bg-blue-50 text-primary">
            <Database className="w-5 h-5" />
          </div>
          <div>
            <h4 className="text-xs font-semibold text-text-primary uppercase tracking-wider">SQLite Local Replicas</h4>
            <p className="text-xs text-text-secondary mt-1">
              Registered SQLite files can be inspected as workspaces with tracked replica operations available through the API workflows.
            </p>
          </div>
        </div>

        <div className="bg-white p-4 rounded-lg border border-border flex items-start gap-3 shadow-xs">
          <div className="p-2.5 rounded-md bg-emerald-50 text-success">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <h4 className="text-xs font-semibold text-text-primary uppercase tracking-wider">Policy Validator</h4>
            <p className="text-xs text-text-secondary mt-1">
              Policy assignments are checked against the detected column type before they are saved.
            </p>
          </div>
        </div>

        <div className="bg-white p-4 rounded-lg border border-border flex items-start gap-3 shadow-xs">
          <div className="p-2.5 rounded-md bg-purple-50 text-[#8B5CF6]">
            <Zap className="w-5 h-5" />
          </div>
          <div>
            <h4 className="text-xs font-semibold text-text-primary uppercase tracking-wider">Semantic Conflict Resolver</h4>
            <p className="text-xs text-text-secondary mt-1">
              Policies include arithmetic merges, deterministic selection, and conflicts held for review; each has limits.
            </p>
          </div>
        </div>

        <div className="bg-white p-4 rounded-lg border border-border flex items-start gap-3 shadow-xs">
          <div className="p-2.5 rounded-md bg-amber-50 text-warning">
            <RefreshCw className="w-5 h-5" />
          </div>
          <div>
            <h4 className="text-xs font-semibold text-text-primary uppercase tracking-wider">CRDT Sync Engine</h4>
            <p className="text-xs text-text-secondary mt-1">
              The engine compares two selected replicas with their common base and reports applied, held, and rejected operations.
            </p>
          </div>
        </div>
      </div>

      {/* High-Level Telemetry Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-text-secondary uppercase">Workspaces</span>
            <Database className="w-4 h-4 text-primary" />
          </div>
          <div className="text-2xl font-bold text-text-primary mt-2">
            {databases.length}
          </div>
          <div className="text-[11px] text-text-muted mt-1">
            SQLite database files registered
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-text-secondary uppercase">Replicas</span>
            <GitBranch className="w-4 h-4 text-primary" />
          </div>
          <div className="text-2xl font-bold text-text-primary mt-2">
            {syncStatus?.registered_replicas ?? 0}
          </div>
          <div className="text-[11px] text-text-muted mt-1">
            Replica databases registered
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-text-secondary uppercase">Active Conflicts</span>
            <Zap className="w-4 h-4 text-warning" />
          </div>
          <div className="text-2xl font-bold text-text-primary mt-2 flex items-center gap-2">
            <span>{(syncStatus?.pending_conflicts || 0) + (syncStatus?.flagged_conflicts || 0)}</span>
            {syncStatus?.flagged_conflicts > 0 && (
              <Badge variant="flagged" size="sm">
                {syncStatus.flagged_conflicts} flagged
              </Badge>
            )}
          </div>
          <div className="text-[11px] text-text-muted mt-1">
            {syncStatus?.resolved_conflicts ?? 0} resolved conflict records
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-text-secondary uppercase">Sync Engine</span>
            <CheckCircle2 className="w-4 h-4 text-success" />
          </div>
          <div className="text-2xl font-bold text-success mt-2 capitalize">
            {syncStatus?.status || 'Ready'}
          </div>
          <div className="text-[11px] text-text-muted mt-1 font-mono">
            Status reported by the sync API
          </div>
        </Card>
      </div>

      {/* Main Sections: Workspaces & Recent Divergences */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Registered Database Workspaces */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-text-primary">Registered Workspaces</h2>
              <p className="text-xs text-text-secondary">Inspect schema, assign policies, or query replica states</p>
            </div>
            <Button
              size="sm"
              variant="secondary"
              icon={Plus}
              onClick={() => navigate('/databases')}
            >
              Manage Databases
            </Button>
          </div>

          {databases.length === 0 ? (
            <Card className="text-center py-10">
              <Database className="w-10 h-10 text-text-muted mx-auto mb-2" />
              <h3 className="text-sm font-semibold text-text-primary">No Workspaces Registered</h3>
              <p className="text-xs text-text-secondary max-w-sm mx-auto mt-1 mb-4">
                The backend seeds workspaces automatically when started with a new empty demo data directory, or register an existing SQLite file.
              </p>
              <Button variant="primary" size="sm" onClick={() => navigate('/databases')}>
                Open Workspaces
              </Button>
            </Card>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {databases.map((db) => (
                <div
                  key={db.id}
                  className="bg-white border border-border rounded-lg p-5 hover:border-primary/50 transition-all shadow-xs flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2">
                        <div className="p-2 rounded-md bg-primary-light text-primary">
                          <Database className="w-4 h-4" />
                        </div>
                        <div>
                          <h3 className="font-semibold text-sm text-text-primary">{db.name}</h3>
                          <span className="text-[10px] font-mono text-text-muted">{db.id}</span>
                        </div>
                      </div>
                      <Badge variant="neutral" size="sm">
                        {db.table_count} {db.table_count === 1 ? 'table' : 'tables'}
                      </Badge>
                    </div>

                    <p className="text-xs text-text-secondary line-clamp-2 mt-1 mb-3">
                      {db.description || 'SQLite database registered with SemanticSync.'}
                    </p>

                    <div className="text-[11px] font-mono bg-gray-50 text-text-muted p-1.5 rounded-sm truncate mb-4">
                      {db.path}
                    </div>
                  </div>

                  <div className="pt-3 border-t border-border flex items-center justify-between gap-2">
                    <button
                      onClick={() => {
                        setSelectedDbId(db.id);
                        navigate(`/workspace/${db.id}/schema`);
                      }}
                      className="text-xs text-primary hover:underline font-medium inline-flex items-center gap-1"
                    >
                      <Layers className="w-3.5 h-3.5" />
                      <span>Policies</span>
                    </button>
                    <button
                      onClick={() => {
                        setSelectedDbId(db.id);
                        navigate(`/workspace/${db.id}/sql`);
                      }}
                      className="text-xs text-text-secondary hover:text-text-primary font-medium inline-flex items-center gap-1"
                    >
                      <Terminal className="w-3.5 h-3.5" />
                      <span>SQL Console</span>
                    </button>
                    <button
                      onClick={() => {
                        setSelectedDbId(db.id);
                        navigate(`/workspace/${db.id}/replicas`);
                      }}
                      className="text-xs text-text-secondary hover:text-text-primary font-medium inline-flex items-center gap-1"
                    >
                      <GitBranch className="w-3.5 h-3.5" />
                      <span>Replicas</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right Col: Recent Conflicts / Flagged Review */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-text-primary">Conflict Activity</h2>
              <p className="text-xs text-text-secondary">Recent divergences detected</p>
            </div>
            <button
              onClick={() => navigate('/conflicts')}
              className="text-xs text-primary font-medium hover:underline inline-flex items-center gap-1"
            >
              <span>View All</span>
              <ArrowRight className="w-3 h-3" />
            </button>
          </div>

          <Card className="p-0">
            {conflictError ? (
              <div className="p-4"><Alert variant="danger" title="Conflict activity unavailable">{conflictError}</Alert></div>
            ) : loadingConflicts ? (
              <div className="p-6 text-center text-xs text-text-muted">Loading conflicts...</div>
            ) : conflicts.length === 0 ? (
              <div className="p-6 text-center">
                <CheckCircle2 className="w-8 h-8 text-success mx-auto mb-2 opacity-80" />
                <h4 className="text-xs font-semibold text-text-primary">No Conflicts Reported</h4>
                <p className="text-[11px] text-text-secondary mt-1">
                  No pending divergences. Use the Sync Hub to create controlled, tracked divergent edits.
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-3 text-xs"
                  onClick={() => navigate('/sync')}
                >
                  Go to Sync Hub
                </Button>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {conflicts.map((c) => (
                  <div
                    key={c.conflict_id}
                    onClick={() => navigate('/conflicts')}
                    className="p-3.5 hover:bg-gray-50 cursor-pointer transition-colors"
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-xs font-semibold text-text-primary">
                          {c.table}.{c.column}
                        </span>
                        <span className="text-[10px] text-text-muted font-mono">#{c.row_id}</span>
                      </div>
                      <Badge variant={c.status} size="sm">
                        {c.status}
                      </Badge>
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-text-secondary">
                      <span className="font-mono">
                        Base: <span className="font-semibold text-text-primary">{String(c.base_value)}</span>
                      </span>
                      <Badge variant="policy" size="sm">
                        {c.policy}
                      </Badge>
                    </div>

                    <div className="mt-1 flex items-center justify-between text-[10px] text-text-muted font-mono bg-gray-50 px-2 py-0.5 rounded-sm">
                      <span>A: {String(c.value_a)}</span>
                      <span>vs</span>
                      <span>B: {String(c.value_b)}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
