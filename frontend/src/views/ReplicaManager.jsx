import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  GitBranch,
  Plus,
  Terminal,
  RefreshCw,
  Clock,
  HardDrive,
  Database,
  ArrowRight,
  CheckCircle2,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Modal } from '../components/ui/Modal';
import { Alert } from '../components/ui/Alert';
import { api } from '../services/api';

export function ReplicaManager() {
  const { dbId } = useParams();
  const navigate = useNavigate();
  const { databases, setSelectedDbId, refreshState } = useApp();

  const [replicas, setReplicas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newReplicaId, setNewReplicaId] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (dbId) setSelectedDbId(dbId);
  }, [dbId, setSelectedDbId]);

  const loadReplicas = async () => {
    if (!dbId) return;
    setLoading(true);
    try {
      const reps = await api.getReplicas(dbId);
      setReplicas(Array.isArray(reps) ? reps : []);
    } catch (err) {
      console.error('Failed to load replicas:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReplicas();
  }, [dbId]);

  const handleCreateReplica = async (e) => {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      await api.createReplica(dbId, newReplicaId.trim());
      await loadReplicas();
      await refreshState();
      setIsCreateOpen(false);
      setNewReplicaId('');
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  const currentDb = databases.find((d) => d.id === dbId);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-primary bg-primary-light px-2 py-0.5 rounded-sm">
              {dbId}
            </span>
            <span className="text-xs text-text-muted">/</span>
            <span className="text-xs font-semibold text-text-secondary">Local Replicas</span>
          </div>
          <h1 className="text-xl font-bold text-text-primary mt-1">
            SQLite Local Replicas Manager
          </h1>
          <p className="text-xs text-text-secondary mt-0.5">
            Local-first devices maintain independent SQLite copies that can diverge offline and synchronize later.
          </p>
        </div>

        <Button
          variant="primary"
          icon={Plus}
          onClick={() => {
            setNewReplicaId(`${dbId}_node_${replicas.length + 1}`);
            setIsCreateOpen(true);
          }}
        >
          Fork New Replica
        </Button>
      </div>

      {/* Replicas Grid */}
      {loading ? (
        <div className="text-center py-16 text-text-muted text-xs">Loading replicas...</div>
      ) : replicas.length === 0 ? (
        <Card className="text-center py-12">
          <GitBranch className="w-12 h-12 text-text-muted mx-auto mb-3" />
          <h3 className="text-sm font-semibold text-text-primary">No Replicas Forked</h3>
          <p className="text-xs text-text-secondary max-w-md mx-auto mt-1 mb-5">
            Fork a replica to create an isolated SQLite database file. Simulate edge device updates and watch how semantic merge policies resolve conflicting values.
          </p>
          <Button
            variant="primary"
            icon={Plus}
            onClick={() => {
              setNewReplicaId(`${dbId}_node_1`);
              setIsCreateOpen(true);
            }}
          >
            Fork First Replica
          </Button>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {replicas.map((rep) => (
            <Card key={rep.replica_id} className="p-5 flex flex-col justify-between">
              <div>
                <div className="flex items-start justify-between gap-2 mb-3">
                  <div className="flex items-center gap-2">
                    <div className="p-2 rounded-md bg-emerald-50 text-success">
                      <GitBranch className="w-4 h-4" />
                    </div>
                    <div>
                      <h3 className="font-bold text-sm text-text-primary font-mono">{rep.replica_id}</h3>
                      <span className="text-[10px] text-text-muted">Parent: {rep.parent_db_id}</span>
                    </div>
                  </div>
                  <Badge variant="success" size="sm">
                    Offline Ready
                  </Badge>
                </div>

                <div className="space-y-1.5 text-xs text-text-secondary bg-gray-50 p-2.5 rounded-md mb-4 font-mono">
                  <div className="flex items-center gap-1.5 text-[11px] truncate text-text-muted" title={rep.db_path}>
                    <HardDrive className="w-3.5 h-3.5 flex-shrink-0" />
                    <span className="truncate">{rep.db_path}</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-[11px] text-text-muted">
                    <Clock className="w-3.5 h-3.5 flex-shrink-0" />
                    <span>{rep.created_at ? new Date(rep.created_at).toLocaleString() : 'Ready'}</span>
                  </div>
                </div>
              </div>

              <div className="pt-3 border-t border-border flex items-center justify-between gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  icon={Terminal}
                  onClick={() => navigate(`/workspace/${dbId}/sql?replica=${rep.replica_id}`)}
                >
                  Query Replica
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  icon={RefreshCw}
                  onClick={() => navigate(`/sync`)}
                >
                  Sync Hub
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Modal: Fork Replica */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Fork SQLite Local Replica"
        subtitle={`Creates a new independent copy of ${currentDb?.name || dbId}`}
      >
        <form onSubmit={handleCreateReplica} className="space-y-4">
          {error && (
            <Alert variant="danger" title="Fork Error">
              {error}
            </Alert>
          )}

          <div>
            <label className="block text-xs font-semibold text-text-primary mb-1">
              Replica Node Identifier *
            </label>
            <input
              type="text"
              required
              value={newReplicaId}
              onChange={(e) => setNewReplicaId(e.target.value)}
              className="w-full text-xs font-mono border border-border rounded-md px-3 py-2 text-text-primary focus:ring-2 focus:ring-primary/20 focus:border-primary outline-hidden"
              placeholder="e.g. tablet_pos_01"
            />
            <p className="text-[11px] text-text-muted mt-1">
              Will be saved to disk as a dedicated SQLite database file and tracked by the CRDT Sync Engine.
            </p>
          </div>

          <div className="pt-3 border-t border-border flex items-center justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setIsCreateOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" size="sm" loading={creating}>
              Create Replica
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
