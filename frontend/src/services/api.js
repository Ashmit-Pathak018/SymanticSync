/**
 * api.js
 * ──────
 * Centralized API service layer for SemanticSync Studio.
 * Connects to the FastAPI backend at /api/v1.
 */

const BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

async function request(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint}`;
  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  };

  if (config.body && typeof config.body === 'object' && !(config.body instanceof FormData)) {
    config.body = JSON.stringify(config.body);
  }

  try {
    const response = await fetch(url, config);
    let data;
    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      data = await response.json();
    } else {
      data = await response.text();
    }

    if (!response.ok) {
      const errorMsg = (data && data.detail) || (typeof data === 'string' ? data : response.statusText);
      const error = new Error(errorMsg);
      error.status = response.status;
      error.data = data;
      throw error;
    }

    return data;
  } catch (err) {
    if (err.name === 'TypeError' && err.message.includes('fetch')) {
      throw new Error(`Unable to connect to SemanticSync API server at ${url}. Is backend running on http://127.0.0.1:8000?`);
    }
    throw err;
  }
}

export const api = {
  // Health
  checkHealth: () => request('/health'),

  // Databases
  getDatabases: () => request('/databases'),
  registerDatabase: (data) => request('/databases', { method: 'POST', body: data }),
  getDatabase: (dbId) => request(`/databases/${encodeURIComponent(dbId)}`),
  getDatabaseSchema: (dbId) => request(`/databases/${encodeURIComponent(dbId)}/schema`),
  getReplicas: (dbId) => request(`/databases/${encodeURIComponent(dbId)}/replicas`),
  createReplica: (dbId, replicaId) =>
    request(`/databases/${encodeURIComponent(dbId)}/replicas`, {
      method: 'POST',
      body: { replica_id: replicaId },
    }),

  // Policies
  getPolicies: (dbId) => request(`/databases/${encodeURIComponent(dbId)}/policies`),
  setPolicies: (dbId, assignments) =>
    request(`/databases/${encodeURIComponent(dbId)}/policies`, {
      method: 'PUT',
      body: { assignments },
    }),
  getPolicyRegistry: () => request('/policies/registry'),
  validatePolicy: (data) =>
    request('/validate-policy', {
      method: 'POST',
      body: data,
    }),

  // Conflicts
  detectConflicts: (dbId, replicaAId, replicaBId) =>
    request('/conflicts/detect', {
      method: 'POST',
      body: { db_id: dbId, replica_a_id: replicaAId, replica_b_id: replicaBId },
    }),
  resolveConflict: (conflictId, resolutionMode, customValue = null) =>
    request('/conflicts/resolve', {
      method: 'POST',
      body: {
        conflict_id: conflictId,
        resolution_mode: resolutionMode,
        custom_value: customValue,
      },
    }),
  getConflicts: (params = {}) => {
    const query = new URLSearchParams();
    if (params.status && params.status !== 'all') query.set('status', params.status);
    if (params.db_id && params.db_id !== 'all') query.set('db_id', params.db_id);
    const queryString = query.toString();
    return request(`/conflicts${queryString ? `?${queryString}` : ''}`);
  },
  getConflict: (conflictId) => request(`/conflicts/${encodeURIComponent(conflictId)}`),

  // Synchronization
  getSyncStatus: () => request('/sync/status'),
  runSync: (dbId, replicaAId, replicaBId, tombstonePolicy = 'FLAG_FOR_REVIEW') =>
    request('/sync/run', {
      method: 'POST',
      body: {
        db_id: dbId,
        replica_a_id: replicaAId,
        replica_b_id: replicaBId,
        tombstone_policy: tombstonePolicy,
      },
    }),
  generateConflict: (payload) =>
    request('/sync/generate-conflict', {
      method: 'POST',
      body: payload,
    }),
  initCheckpointStore: () =>
    request('/sync/checkpoint-store/initialize', {
      method: 'POST',
    }),
  compactSyncLogs: (dbId) =>
    request('/sync/compact', {
      method: 'POST',
      body: { db_id: dbId },
    }),

  // Quarantine Management
  listQuarantine: (params = {}) => {
    const query = new URLSearchParams();
    if (params.table && params.table !== 'all') query.set('table', params.table);
    if (params.status && params.status !== 'all') query.set('status', params.status);
    if (params.db_id && params.db_id !== 'all') query.set('db_id', params.db_id);
    const queryString = query.toString();
    return request(`/quarantine${queryString ? `?${queryString}` : ''}`);
  },
  getQuarantineRecord: (quarantineId, dbId = null) => {
    const query = new URLSearchParams();
    if (dbId) query.set('db_id', dbId);
    const queryString = query.toString();
    return request(`/quarantine/${encodeURIComponent(quarantineId)}${queryString ? `?${queryString}` : ''}`);
  },
  resolveQuarantine: (quarantineId, action, newParentRowId = null, dbId = null) => {
    const query = new URLSearchParams();
    if (dbId) query.set('db_id', dbId);
    const queryString = query.toString();
    return request(`/quarantine/${encodeURIComponent(quarantineId)}/resolve${queryString ? `?${queryString}` : ''}`, {
      method: 'POST',
      body: {
        action,
        new_parent_row_id: newParentRowId,
      },
    });
  },

  // SQL Query Console
  executeQuery: (dbId, sql, replicaId = null, allowWrite = false) =>
    request('/query', {
      method: 'POST',
      body: {
        db_id: dbId,
        replica_id: replicaId || null,
        sql,
        allow_write: allowWrite,
      },
    }),

  // Benchmark & Metrics
  runBenchmark: (workload) =>
    request('/benchmark/run', {
      method: 'POST',
      body: { workload },
    }),
  runStressBenchmark: (params = {}) =>
    request('/benchmark/stress', {
      method: 'POST',
      body: {
        num_operations: params.num_operations ?? 1000,
        conflict_density: params.conflict_density ?? 0.20,
        seed: params.seed ?? 42,
        export_artifacts: params.export_artifacts ?? true,
      },
    }),
  getMetrics: () => request('/metrics'),
  getBenchmarkArtifacts: () => request('/benchmark/artifacts'),
  getBenchmarkArtifactDownloadUrl: (filename) =>
    `${BASE_URL}/benchmark/artifacts/${encodeURIComponent(filename)}`,

  // Seeding
  seedWorkload: (workload = 'all') =>
    request('/seed', {
      method: 'POST',
      body: { workload },
    }),
};
