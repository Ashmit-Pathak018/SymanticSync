import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Database,
  Plus,
  GitBranch,
  Layers,
  Terminal,
  Calendar,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Modal } from '../components/ui/Modal';
import { Alert } from '../components/ui/Alert';
import { api } from '../services/api';

export function Databases() {
  const { databases, refreshState, setSelectedDbId, refreshCounter } = useApp();
  const navigate = useNavigate();

  const [isRegisterOpen, setIsRegisterOpen] = useState(false);
  const [isCreateReplicaOpen, setIsCreateReplicaOpen] = useState(false);
  const [selectedDbForReplica, setSelectedDbForReplica] = useState(null);

  // Form states
  const [formName, setFormName] = useState('');
  const [formPath, setFormPath] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [registering, setRegistering] = useState(false);
  const [registerError, setRegisterError] = useState(null);

  const [replicaIdInput, setReplicaIdInput] = useState('');
  const [creatingReplica, setCreatingReplica] = useState(false);
  const [replicaError, setReplicaError] = useState(null);

  // Map of replicas per database
  const [replicasMap, setReplicasMap] = useState({});
  const [replicaErrors, setReplicaErrors] = useState({});
  const [loadingReplicas, setLoadingReplicas] = useState(false);

  useEffect(() => {
    async function fetchAllReplicas() {
      setLoadingReplicas(true);
      const results = {};
      const errors = {};
      for (const db of databases) {
        try {
          const reps = await api.getReplicas(db.id);
          results[db.id] = Array.isArray(reps) ? reps : [];
        } catch (err) {
          results[db.id] = [];
          errors[db.id] = err.message || 'Replica list request failed.';
        }
      }
      setReplicasMap(results);
      setReplicaErrors(errors);
      setLoadingReplicas(false);
    }
    if (databases.length > 0) {
      fetchAllReplicas();
    }
  }, [databases, refreshCounter]);

  const handleRegister = async (e) => {
    e.preventDefault();
    setRegistering(true);
    setRegisterError(null);
    try {
      await api.registerDatabase({
        name: formName.trim(),
        path: formPath.trim(),
        description: formDesc.trim(),
      });
      await refreshState();
      setIsRegisterOpen(false);
      setFormName('');
      setFormPath('');
      setFormDesc('');
    } catch (err) {
      setRegisterError(err.message);
    } finally {
      setRegistering(false);
    }
  };

  const handleCreateReplica = async (e) => {
    e.preventDefault();
    if (!selectedDbForReplica) return;
    setCreatingReplica(true);
    setReplicaError(null);
    try {
      await api.createReplica(selectedDbForReplica.id, replicaIdInput.trim());
      // Refresh replicas map
      const reps = await api.getReplicas(selectedDbForReplica.id);
      setReplicasMap((prev) => ({
        ...prev,
        [selectedDbForReplica.id]: reps,
      }));
      await refreshState();
      setIsCreateReplicaOpen(false);
      setReplicaIdInput('');
    } catch (err) {
      setReplicaError(err.message);
    } finally {
      setCreatingReplica(false);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-text-primary">SQLite Workspaces & Replicas</h1>
          <p className="text-xs text-text-secondary mt-1">
            Inspect registered databases, assign policies, and create independent replica files for tracked pairwise sync.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="primary"
            icon={Plus}
            onClick={() => setIsRegisterOpen(true)}
          >
            Register Database
          </Button>
        </div>
      </div>

      {/* Database Cards */}
      {databases.length === 0 ? (
        <Card className="text-center py-12">
          <Database className="w-12 h-12 text-text-muted mx-auto mb-3" />
          <h3 className="text-sm font-semibold text-text-primary">No Workspaces Registered</h3>
          <p className="text-xs text-text-secondary max-w-md mx-auto mt-1 mb-5">
            Register an existing SQLite database file (.db). A fresh demo data directory is populated automatically when the backend starts.
          </p>
          <Button
            variant="primary"
            icon={Plus}
            onClick={() => setIsRegisterOpen(true)}
          >
            Register SQLite Database
          </Button>
        </Card>
      ) : (
        <div className="space-y-4">
          {databases.map((db) => {
            const reps = replicasMap[db.id] || [];
            return (
              <div
                key={db.id}
                className="bg-white border border-border rounded-xl p-5 shadow-xs hover:border-primary/40 transition-all"
              >
                <div className="flex flex-col md:flex-row md:items-start justify-between gap-4 pb-4 border-b border-border">
                  <div className="flex items-start gap-3">
                    <div className="p-2.5 rounded-lg bg-primary-light text-primary flex-shrink-0 mt-0.5">
                      <Database className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <h2 className="text-base font-bold text-text-primary">{db.name}</h2>
                        <span className="text-[11px] font-mono text-text-muted bg-gray-100 px-2 py-0.5 rounded-sm">
                          ID: {db.id}
                        </span>
                        <Badge variant="neutral" size="sm">
                          {db.table_count} {db.table_count === 1 ? 'table' : 'tables'}
                        </Badge>
                      </div>
                      <p className="text-xs text-text-secondary mt-1 max-w-2xl">
                        {db.description || 'Registered SQLite workspace.'}
                      </p>
                      <div className="flex items-center gap-4 text-xs text-text-muted mt-2 font-mono">
                        <span className="truncate max-w-md" title={db.path}>
                          Path: {db.path}
                        </span>
                        <span className="flex items-center gap-1 font-sans text-[11px]">
                          <Calendar className="w-3 h-3" />
                          {db.created_at ? new Date(db.created_at).toLocaleDateString() : 'Active'}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <Button
                      size="sm"
                      variant="outline"
                      icon={Layers}
                      onClick={() => {
                        setSelectedDbId(db.id);
                        navigate(`/workspace/${db.id}/schema`);
                      }}
                    >
                      Schema Policies
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      icon={Terminal}
                      onClick={() => {
                        setSelectedDbId(db.id);
                        navigate(`/workspace/${db.id}/sql`);
                      }}
                    >
                      SQL Console
                    </Button>
                    <Button
                      size="sm"
                      variant="primary"
                      icon={Plus}
                      onClick={() => {
                        setSelectedDbForReplica(db);
                        setReplicaIdInput(`${db.id}_replica_${(reps.length || 0) + 1}`);
                        setIsCreateReplicaOpen(true);
                      }}
                    >
                      Fork Replica
                    </Button>
                  </div>
                </div>

                {/* Replicas Strip */}
                <div className="pt-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold text-text-secondary flex items-center gap-1.5 uppercase tracking-wider">
                      <GitBranch className="w-3.5 h-3.5 text-primary" />
                      <span>Replicas ({reps.length})</span>
                    </span>
                    <button
                      onClick={() => {
                        setSelectedDbId(db.id);
                        navigate(`/workspace/${db.id}/replicas`);
                      }}
                      className="text-xs text-primary hover:underline font-medium"
                    >
                      View All Replicas &rarr;
                    </button>
                  </div>

                  {loadingReplicas ? (
                    <div className="text-xs text-text-muted bg-gray-50 rounded-lg p-3 text-center">Loading replica list…</div>
                  ) : replicaErrors[db.id] ? (
                    <Alert variant="danger" title="Replica list unavailable">
                      {replicaErrors[db.id]} Refresh or check the backend before treating this workspace as empty.
                    </Alert>
                  ) : reps.length === 0 ? (
                    <div className="text-xs text-text-muted bg-gray-50 rounded-lg p-3 text-center">
                      No replicas forked yet. Fork a replica to simulate offline edits.
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5">
                      {reps.map((rep) => (
                        <div
                          key={rep.replica_id}
                          className="bg-gray-50/80 border border-border/80 rounded-lg p-2.5 flex items-center justify-between text-xs"
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="w-2 h-2 rounded-full bg-primary flex-shrink-0" />
                            <div className="min-w-0">
                              <span className="font-mono font-medium text-text-primary block truncate">
                                {rep.replica_id}
                              </span>
                              <span className="font-mono text-[10px] text-text-muted block truncate max-w-[150px]">
                                {rep.db_path}
                              </span>
                            </div>
                          </div>
                          <button
                            onClick={() => {
                              setSelectedDbId(db.id);
                              navigate(`/workspace/${db.id}/sql?replica=${rep.replica_id}`);
                            }}
                            className="p-1 hover:bg-white rounded text-primary text-xs"
                            title="Query replica in SQL console"
                          >
                            <Terminal className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Modal: Register Database */}
      <Modal
        isOpen={isRegisterOpen}
        onClose={() => setIsRegisterOpen(false)}
        title="Register SQLite Database Workspace"
        subtitle="Point SemanticSync to any standard SQLite file (.db)"
      >
        <form onSubmit={handleRegister} className="space-y-4">
          {registerError && (
            <Alert variant="danger" title="Registration Failed">
              {registerError}
            </Alert>
          )}

          <div>
            <label className="block text-xs font-semibold text-text-primary mb-1">
              Workspace Name *
            </label>
            <input
              type="text"
              required
              placeholder="e.g. Production Analytics"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              className="w-full text-xs border border-border rounded-md px-3 py-2 text-text-primary focus:ring-2 focus:ring-primary/20 focus:border-primary outline-hidden"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-primary mb-1">
              Database File Path *
            </label>
            <input
              type="text"
              required
              placeholder="e.g. data/my_app.db or absolute path"
              value={formPath}
              onChange={(e) => setFormPath(e.target.value)}
              className="w-full text-xs font-mono border border-border rounded-md px-3 py-2 text-text-primary focus:ring-2 focus:ring-primary/20 focus:border-primary outline-hidden"
            />
            <p className="text-[11px] text-text-muted mt-1">
              Must be an existing SQLite database file. SemanticSync uses SQLite PRAGMAs to inspect schema without changing your data.
            </p>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-primary mb-1">
              Description (Optional)
            </label>
            <textarea
              rows={2}
              placeholder="Brief summary of domain and tables"
              value={formDesc}
              onChange={(e) => setFormDesc(e.target.value)}
              className="w-full text-xs border border-border rounded-md px-3 py-2 text-text-primary focus:ring-2 focus:ring-primary/20 focus:border-primary outline-hidden"
            />
          </div>

          <div className="pt-3 border-t border-border flex items-center justify-end gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setIsRegisterOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="sm"
              loading={registering}
            >
              Register Workspace
            </Button>
          </div>
        </form>
      </Modal>

      {/* Modal: Fork Replica */}
      <Modal
        isOpen={isCreateReplicaOpen}
        onClose={() => setIsCreateReplicaOpen(false)}
        title={`Fork Offline Replica from ${selectedDbForReplica?.name || ''}`}
        subtitle="Creates an isolated SQLite copy for offline editing and local-first simulation"
      >
        <form onSubmit={handleCreateReplica} className="space-y-4">
          {replicaError && (
            <Alert variant="danger" title="Fork Failed">
              {replicaError}
            </Alert>
          )}

          <div>
            <label className="block text-xs font-semibold text-text-primary mb-1">
              Replica Node ID *
            </label>
            <input
              type="text"
              required
              placeholder="e.g. device_tablet_01"
              value={replicaIdInput}
              onChange={(e) => setReplicaIdInput(e.target.value)}
              className="w-full text-xs font-mono border border-border rounded-md px-3 py-2 text-text-primary focus:ring-2 focus:ring-primary/20 focus:border-primary outline-hidden"
            />
            <p className="text-[11px] text-text-muted mt-1">
              Identifies the edge device replica. Changes will be tracked with Hybrid Logical Clocks (HLC).
            </p>
          </div>

          <div className="pt-3 border-t border-border flex items-center justify-end gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setIsCreateReplicaOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="sm"
              loading={creatingReplica}
            >
              Create Replica File
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
