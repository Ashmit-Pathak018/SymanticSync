import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppProvider } from '../context/AppContext';
import { SyncHub } from '../views/SyncHub';
import { api } from '../services/api';

vi.mock('../services/api', () => ({
  api: {
    checkHealth: vi.fn(),
    getDatabases: vi.fn(),
    getSyncStatus: vi.fn(),
    getPolicyRegistry: vi.fn(),
    getReplicas: vi.fn(),
    runSync: vi.fn(),
    detectConflicts: vi.fn(),
    initCheckpointStore: vi.fn(),
    compactSyncLogs: vi.fn(),
  },
}));

describe('Sync Hub conflict review', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.checkHealth.mockResolvedValue({ status: 'healthy' });
    api.getDatabases.mockResolvedValue([{ id: 'db_inventory', name: 'Inventory', table_count: 1 }]);
    api.getSyncStatus.mockResolvedValue({ status: 'ready', registered_replicas: 2 });
    api.getPolicyRegistry.mockResolvedValue([]);
    api.getReplicas.mockResolvedValue([
      { replica_id: 'inventory_device_a' },
      { replica_id: 'inventory_device_b' },
    ]);
    api.runSync.mockResolvedValue({
      status: 'completed', total_conflicts: 1, auto_resolved: 0,
      flagged_for_review: 1, applied_changes: [], duration_ms: 1,
      skipped_tables: [], rejected_operations: [],
    });
    api.detectConflicts.mockResolvedValue([{ conflict_id: 'review-1', status: 'pending' }]);
  });

  afterEach(() => vi.restoreAllMocks());

  it('refreshes the persisted conflict list after sync and exposes remaining review work', async () => {
    render(
      <MemoryRouter>
        <AppProvider>
          <SyncHub />
        </AppProvider>
      </MemoryRouter>
    );

    const runSync = await screen.findByRole('button', { name: /run pairwise semantic sync/i });
    await waitFor(() => expect(runSync.disabled).toBe(false));
    fireEvent.click(runSync);

    await waitFor(() => {
      expect(api.runSync).toHaveBeenCalledWith(
        'db_inventory', 'inventory_device_a', 'inventory_device_b', 'FLAG_FOR_REVIEW'
      );
      expect(api.detectConflicts).toHaveBeenCalledWith(
        'db_inventory', 'inventory_device_a', 'inventory_device_b'
      );
      expect(screen.getByText(/remaining conflicts saved for review/i)).toBeDefined();
      expect(screen.getByRole('button', { name: /open conflicts/i })).toBeDefined();
    });
  });
});
