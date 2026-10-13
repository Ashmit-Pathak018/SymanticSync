import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppProvider } from '../context/AppContext';
import { Quarantine } from '../views/Quarantine';
import { Conflicts } from '../views/Conflicts';
import { SyncHub } from '../views/SyncHub';
import { Analytics } from '../views/Analytics';
import { api } from '../services/api';

// Mock the API module
vi.mock('../services/api', () => ({
  api: {
    checkHealth: vi.fn(),
    getDatabases: vi.fn(),
    getReplicas: vi.fn(),
    getSyncStatus: vi.fn(),
    getPolicyRegistry: vi.fn(),
    getDatabaseSchema: vi.fn(),
    getConflicts: vi.fn(),
    resolveConflict: vi.fn(),
    listQuarantine: vi.fn(),
    getQuarantineRecord: vi.fn(),
    resolveQuarantine: vi.fn(),
    runSync: vi.fn(),
    initCheckpointStore: vi.fn(),
    compactSyncLogs: vi.fn(),
    generateConflict: vi.fn(),
    getMetrics: vi.fn(),
    runBenchmark: vi.fn(),
    runStressBenchmark: vi.fn(),
    getBenchmarkArtifacts: vi.fn(),
    getBenchmarkArtifactDownloadUrl: vi.fn((file) => `/api/v1/benchmark/artifacts/${file}`),
  },
}));

describe('Phase 7 Integration Tests', () => {
  const mockDatabases = [
    { id: 'db_test', name: 'Test DB', table_count: 2 },
  ];

  const mockReplicas = [
    { replica_id: 'rep_1', db_id: 'db_test', db_path: '/tmp/rep1.sqlite' },
    { replica_id: 'rep_2', db_id: 'db_test', db_path: '/tmp/rep2.sqlite' },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    api.checkHealth.mockResolvedValue({ status: 'healthy' });
    api.getDatabases.mockResolvedValue(mockDatabases);
    api.getReplicas.mockResolvedValue(mockReplicas);
    api.getSyncStatus.mockResolvedValue({
      status: 'ready',
      registered_databases: 1,
      registered_replicas: 2,
      total_conflicts: 1,
      pending_conflicts: 1,
      flagged_conflicts: 0,
      resolved_conflicts: 0,
      checkpoint_store: { status: 'ready', store_id: 'store_123' },
    });
    api.getPolicyRegistry.mockResolvedValue({
      SUM: { name: 'Additive Sum' },
      LWW: { name: 'Last-Write-Wins' },
    });
  });

  describe('Quarantine View Tests', () => {
    const mockQuarantined = [
      {
        quarantine_id: 'q_101',
        table_name: 'order_items',
        row_id: '42',
        parent_table: 'orders',
        parent_row_id: '999',
        reason: 'Parent key 999 missing in orders',
        row_payload: JSON.stringify({ id: 42, order_id: 999, product: 'Widget', qty: 5 }),
        status: 'quarantined',
        quarantined_at: '2026-10-13T10:00:00Z',
      },
    ];

    it('renders quarantined rows with table, parent info, reason, and payload', async () => {
      api.listQuarantine.mockResolvedValue(mockQuarantined);

      render(
        <MemoryRouter>
          <AppProvider>
            <Quarantine />
          </AppProvider>
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('order_items')).toBeDefined();
        expect(screen.getByText(/Row #42/i)).toBeDefined();
        expect(screen.getByText(/Parent key 999 missing in orders/i)).toBeDefined();
      });
    });

    it('expands row, performs parent relinking, and reports validation error on failure', async () => {
      api.listQuarantine.mockResolvedValue(mockQuarantined);
      api.resolveQuarantine.mockRejectedValue({
        data: { detail: 'Foreign key constraint violation: order_id 888 does not exist' },
      });

      render(
        <MemoryRouter>
          <AppProvider>
            <Quarantine />
          </AppProvider>
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('order_items')).toBeDefined();
      });

      // Expand accordion
      fireEvent.click(screen.getByText('order_items'));

      // Find input and enter new parent ID
      await waitFor(() => {
        expect(screen.getByPlaceholderText('e.g. 2')).toBeDefined();
      });
      const input = screen.getByPlaceholderText('e.g. 2');
      fireEvent.change(input, { target: { value: '888' } });

      const relinkBtn = screen.getByRole('button', { name: /Relink Parent & Restore/i });
      fireEvent.click(relinkBtn);

      await waitFor(() => {
        expect(api.resolveQuarantine).toHaveBeenCalled();
        expect(screen.getByText(/Foreign key constraint violation: order_id 888 does not exist/i)).toBeDefined();
      });
    });
  });

  describe('Conflicts View Tests', () => {
    const mockConflicts = [
      {
        conflict_id: 'c_201',
        db_id: 'db_test',
        table: 'users',
        column: 'email',
        row_id: 1,
        conflict_type: 'UNIQUE_COLLISION',
        base_value: 'alice@example.com',
        value_a: 'alice_new@example.com',
        value_b: 'alice_other@example.com',
        policy: 'REJECT',
        status: 'pending',
      },
    ];

    it('displays full conflict mutation details and expands to view payload values', async () => {
      api.getConflicts.mockResolvedValue(mockConflicts);

      render(
        <MemoryRouter>
          <AppProvider>
            <Conflicts />
          </AppProvider>
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('users.email')).toBeDefined();
      });

      // Expand the conflict accordion
      fireEvent.click(screen.getByText('users.email'));

      await waitFor(() => {
        expect(screen.getByText('alice_new@example.com')).toBeDefined();
        expect(screen.getByText('alice_other@example.com')).toBeDefined();
      });
    });
  });

  describe('SyncHub Checkpoints & Compaction Tests', () => {
    it('renders tombstone policy selector and displays blocked checkpoint without claiming compacted', async () => {
      api.compactSyncLogs.mockResolvedValue({
        status: 'blocked',
        pruned: 0,
        reason: 'Unacknowledged operations exist across replicas',
        blocked_checkpoints: [
          { checkpoint_id: 'chk_blocked_1', reason: 'Missing ACK from rep_2' },
        ],
      });

      render(
        <MemoryRouter>
          <AppProvider>
            <SyncHub />
          </AppProvider>
        </MemoryRouter>
      );

      // Wait for compact button to become enabled
      await waitFor(() => {
        const compactBtn = screen.getByRole('button', { name: /Run Causal Compaction/i });
        expect(compactBtn.disabled).toBe(false);
      });

      // Verify tombstone policy is visible
      expect(screen.getByText(/Tombstone Merge Policy/i)).toBeDefined();

      // Trigger causal compaction
      const compactBtn = screen.getByRole('button', { name: /Run Causal Compaction/i });
      fireEvent.click(compactBtn);

      await waitFor(() => {
        expect(api.compactSyncLogs).toHaveBeenCalledWith('db_test');
        // Must show blocked warning, never claim compacted
        expect(screen.getByText(/Compaction Blocked \(Safety Invariant Protected\)/i)).toBeDefined();
        expect(screen.getByText(/Unacknowledged operations exist across replicas/i)).toBeDefined();
        expect(screen.getByText(/chk_blocked_1/i)).toBeDefined();
      });
    });
  });

  describe('Analytics Benchmark Suite Tests', () => {
    const mockArtifacts = [
      {
        filename: 'benchmark_1000_20pct_42.json',
        format: 'json',
        size_bytes: 4096,
        modified_at: '2026-10-13T10:00:00Z',
        num_operations: 1000,
        conflict_density_pct: 20,
        seed: 42,
      },
    ];

    it('allows switching between tabs and lists empirical artifacts with preview and download', async () => {
      api.getMetrics.mockResolvedValue({
        workloads: {
          inventory: {
            workload: 'inventory',
            baseline_scr: 40.0,
            semantic_sync_scr: 100.0,
            semantic_sync_convergence_rate: 100.0,
            total_conflicts_evaluated: 5,
            correct_semantic_outcomes: 5,
            resolution_overhead_ms: 0.12,
          },
        },
      });
      api.getBenchmarkArtifacts.mockResolvedValue(mockArtifacts);

      render(
        <MemoryRouter>
          <AppProvider>
            <Analytics />
          </AppProvider>
        </MemoryRouter>
      );

      // Default tab: Domain Workloads
      await waitFor(() => {
        expect(screen.getByText(/Research Benchmark Dashboard/i)).toBeDefined();
        expect(screen.getByText(/Primary Empirical Metric/i)).toBeDefined();
      });

      // Switch to Matrix Artifacts tab
      const artifactsTab = screen.getByRole('button', { name: /Matrix Artifacts/i });
      fireEvent.click(artifactsTab);

      await waitFor(() => {
        expect(screen.getByText('benchmark_1000_20pct_42.json')).toBeDefined();
        expect(screen.getByRole('button', { name: /Preview/i })).toBeDefined();
      });
    });
  });
});
