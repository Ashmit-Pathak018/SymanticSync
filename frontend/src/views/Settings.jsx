import React, { useState } from 'react';
import {
  BookOpen,
  Sparkles,
  ShieldCheck,
  RefreshCw,
  Cpu,
  Layers,
  Database,
  CheckCircle2,
  ExternalLink,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Alert } from '../components/ui/Alert';
import { api } from '../services/api';

export function Settings() {
  const { policyRegistry, refreshState } = useApp();
  const [seeding, setSeeding] = useState(false);
  const [seedMsg, setSeedMsg] = useState(null);

  const handleSeed = async (workload) => {
    setSeeding(true);
    setSeedMsg(null);
    try {
      await api.seedWorkload(workload);
      await refreshState();
      setSeedMsg(`Successfully re-seeded '${workload}' demo data.`);
      setTimeout(() => setSeedMsg(null), 4000);
    } catch (err) {
      alert(`Seeding failed: ${err.message}`);
    } finally {
      setSeeding(false);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Policy Registry & System Documentation</h1>
          <p className="text-xs text-text-secondary mt-1">
            Live catalog of registered attribute merge policies and architectural guidelines.
          </p>
        </div>
      </div>

      {seedMsg && (
        <Alert variant="success" title="Seeder Operation Complete">
          {seedMsg}
        </Alert>
      )}

      {/* Policies Catalog */}
      <div className="space-y-4">
        <h2 className="text-sm font-bold text-text-primary uppercase tracking-wider">
          Registered Merge Policies ({policyRegistry.length})
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {policyRegistry.map((p) => {
            const types = Array.isArray(p.compatible_types)
              ? p.compatible_types
              : Array.from(p.compatible_types || []);

            return (
              <Card key={p.name} className="p-5 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="font-mono text-base font-bold text-primary">{p.name}</span>
                    <Badge variant={p.symmetric ? 'success' : 'neutral'} size="sm">
                      {p.symmetric ? 'Symmetric' : 'Asymmetric'}
                    </Badge>
                  </div>

                  <p className="text-xs text-text-secondary mb-4 leading-relaxed">
                    {p.description}
                  </p>
                </div>

                <div className="pt-3 border-t border-border">
                  <div className="text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1.5">
                    Compatible SQLite Types:
                  </div>
                  <div className="flex flex-wrap gap-1 font-mono">
                    {types.length === 0 || types.includes('*') ? (
                      <span className="text-xs bg-gray-100 text-text-primary px-2 py-0.5 rounded">
                        Any Datatype
                      </span>
                    ) : (
                      types.map((t) => (
                        <span
                          key={t}
                          className="text-xs bg-blue-50 text-primary border border-blue-200/60 px-2 py-0.5 rounded"
                        >
                          {t}
                        </span>
                      ))
                    )}
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      </div>

      {/* Seeder & Demo Management */}
      <Card title="Demo Workload Management" subtitle="Reset or re-populate benchmark datasets">
        <p className="text-xs text-text-secondary mb-4">
          Seeding resets the SQLite base databases, creates 3 edge replicas for each (<code>device_a</code>, <code>device_b</code>, <code>device_c</code>), assigns recommended policies, and injects controlled conflict scenarios for evaluation.
        </p>

        <div className="flex flex-wrap gap-3">
          <Button
            variant="primary"
            size="sm"
            icon={Sparkles}
            loading={seeding}
            onClick={() => handleSeed('all')}
          >
            Re-Seed All 3 Workloads
          </Button>
          <Button
            variant="secondary"
            size="sm"
            loading={seeding}
            onClick={() => handleSeed('inventory')}
          >
            Seed Inventory Only
          </Button>
          <Button
            variant="secondary"
            size="sm"
            loading={seeding}
            onClick={() => handleSeed('notes')}
          >
            Seed Notes Only
          </Button>
          <Button
            variant="secondary"
            size="sm"
            loading={seeding}
            onClick={() => handleSeed('health')}
          >
            Seed Healthcare Only
          </Button>
        </div>
      </Card>

      {/* Architectural Guidelines */}
      <Card title="Architecture Principles & North Star">
        <div className="space-y-3 text-xs text-text-secondary leading-relaxed">
          <p>
            <strong className="text-text-primary">1. Keep SQL and SQLite:</strong> The underlying database engine is standard SQLite. Applications continue to run standard SQL transactions.
          </p>
          <p>
            <strong className="text-text-primary">2. The Build Principle:</strong> <em>"CRDT handles convergence; the semantic middleware handles the meaning of a conflict."</em>
          </p>
          <p>
            <strong className="text-text-primary">3. Absolute Domain Independence:</strong> The core engine never hardcodes business assumptions. It operates purely on column datatypes and explicitly configured merge policies.
          </p>
          <p>
            <strong className="text-text-primary">4. Fail Fast with Explicit Validation:</strong> Schema and policy compatibility are validated before runtime execution. Incompatible configurations are caught with HTTP 422.
          </p>
          <p>
            <strong className="text-text-primary">5. Determinism & Idempotency:</strong> Conflict resolution algorithms produce identical output on all replicas given identical inputs.
          </p>
        </div>
      </Card>
    </div>
  );
}
