import React from 'react';
import { useApp } from '../context/AppContext';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';

export function Settings() {
  const { policyRegistry } = useApp();

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

      {/* Architectural Guidelines */}
      <Card title="How to Read the Policy Catalog">
        <div className="space-y-3 text-xs text-text-secondary leading-relaxed">
          <p>
            <strong className="text-text-primary">Storage:</strong> Workspaces and replicas are SQLite databases. Tracked mutations use the SemanticSync API; SQL Console statements bypass replication logging and quarantine workflows.
          </p>
          <p>
            <strong className="text-text-primary">Policy scope:</strong> A policy describes how the engine handles supported conflicting column changes. Its behavior depends on operation history and the tested schedule.
          </p>
          <p>
            <strong className="text-text-primary">Bounds:</strong> BOUNDED_SUM keeps out-of-range candidates pending for review; it does not clamp or discard them.
          </p>
          <p>
            <strong className="text-text-primary">Review:</strong> REJECT and unsafe bounded operations may remain unresolved until a user reviews them. Check the Sync Hub and Conflicts view for held outcomes.
          </p>
          <p>
            <strong className="text-text-primary">Evidence boundary:</strong> Deterministic selection does not establish causality, arbitrary-order convergence, or semantic correctness for every application.
          </p>
        </div>
      </Card>
    </div>
  );
}
