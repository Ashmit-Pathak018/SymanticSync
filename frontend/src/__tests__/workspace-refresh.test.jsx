import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { AppProvider, useApp } from '../context/AppContext';
import { TopBar } from '../components/layout/TopBar';
import { SchemaEditor } from '../views/SchemaEditor';
import { api } from '../services/api';

// Mock the API module
vi.mock('../services/api', () => ({
  api: {
    checkHealth: vi.fn(),
    getDatabases: vi.fn(),
    getSyncStatus: vi.fn(),
    getPolicyRegistry: vi.fn(),
    getDatabaseSchema: vi.fn(),
    validatePolicy: vi.fn(),
    savePolicies: vi.fn(),
    seedWorkload: vi.fn(),
  },
}));

describe('Workspace Switching and Global Refresh Tests', () => {
  const mockDatabases = [
    { id: 'db_inventory', name: 'Inventory DB', table_count: 2 },
    { id: 'db_notes', name: 'Notes DB', table_count: 1 },
  ];

  const mockInventorySchema = {
    database_id: 'db_inventory',
    tables: [
      {
        table_name: 'products',
        columns: [
          { name: 'id', type: 'INTEGER', is_pk: true, policy: 'LWW', normalized_type: 'INTEGER' },
          { name: 'price', type: 'REAL', is_pk: false, policy: 'LWW', normalized_type: 'REAL' },
        ],
      },
    ],
  };

  const mockNotesSchema = {
    database_id: 'db_notes',
    tables: [
      {
        table_name: 'notes',
        columns: [
          { name: 'id', type: 'INTEGER', is_pk: true, policy: 'LWW', normalized_type: 'INTEGER' },
          { name: 'content', type: 'TEXT', is_pk: false, policy: 'APPEND', normalized_type: 'TEXT' },
        ],
      },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    api.checkHealth.mockResolvedValue({ status: 'healthy' });
    api.getDatabases.mockResolvedValue(mockDatabases);
    api.getSyncStatus.mockResolvedValue({ total_events: 10, total_conflicts: 2 });
    api.getPolicyRegistry.mockResolvedValue(['SUM', 'AVG', 'APPEND', 'LWW', 'REJECT', 'MIN', 'MAX']);
    api.getDatabaseSchema.mockImplementation(async (dbId) => {
      if (dbId === 'db_notes') return mockNotesSchema;
      return mockInventorySchema;
    });
    api.validatePolicy.mockResolvedValue({ valid: true, error_message: null });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('updates selectedDbId and navigates when workspace is changed in TopBar', async () => {
    function LocationTracker() {
      const { selectedDbId } = useApp();
      return <div data-testid="active-db">{selectedDbId}</div>;
    }

    render(
      <MemoryRouter initialEntries={['/workspace/db_inventory/schema']}>
        <AppProvider>
          <TopBar />
          <LocationTracker />
          <Routes>
            <Route
              path="/workspace/:dbId/schema"
              element={<div data-testid="schema-route">Schema View</div>}
            />
          </Routes>
        </AppProvider>
      </MemoryRouter>
    );

    // Wait for databases to load
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /active workspace/i })).toBeDefined();
    });

    const select = screen.getByRole('combobox', { name: /active workspace/i });
    expect(select.value).toBe('db_inventory');

    // Switch workspace to Notes DB
    await act(async () => {
      fireEvent.change(select, { target: { value: 'db_notes' } });
    });

    // Check that context updated
    await waitFor(() => {
      expect(screen.getByTestId('active-db').textContent).toBe('db_notes');
    });
  });

  it('prompts confirmation when switching workspace with unsaved edits and respects cancellation', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);

    function UnsavedTrigger() {
      const { setUnsavedChanges, selectedDbId } = useApp();
      return (
        <div>
          <button onClick={() => setUnsavedChanges(true)}>Make Dirty</button>
          <span data-testid="db-indicator">{selectedDbId}</span>
        </div>
      );
    }

    render(
      <MemoryRouter initialEntries={['/workspace/db_inventory/schema']}>
        <AppProvider>
          <TopBar />
          <UnsavedTrigger />
        </AppProvider>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /active workspace/i })).toBeDefined();
    });

    // Trigger dirty state
    fireEvent.click(screen.getByText('Make Dirty'));

    const select = screen.getByRole('combobox', { name: /active workspace/i });

    // Attempt to switch workspace while dirty, user cancels
    await act(async () => {
      fireEvent.change(select, { target: { value: 'db_notes' } });
    });

    expect(confirmSpy).toHaveBeenCalled();
    // Selection should remain db_inventory because user cancelled
    expect(screen.getByTestId('db-indicator').textContent).toBe('db_inventory');

    // Now user accepts prompt
    confirmSpy.mockReturnValue(true);
    await act(async () => {
      fireEvent.change(select, { target: { value: 'db_notes' } });
    });

    // Selection should now switch to db_notes
    await waitFor(() => {
      expect(screen.getByTestId('db-indicator').textContent).toBe('db_notes');
    });
  });

  it('SchemaEditor immediately resets previous workspace data and loads new workspace schema', async () => {
    function RouteSwitcher() {
      const navigate = useNavigate();
      return (
        <button data-testid="route-switch-trigger" onClick={() => navigate('/workspace/db_notes/schema')}>
          Switch Workspace
        </button>
      );
    }

    render(
      <MemoryRouter initialEntries={['/workspace/db_inventory/schema']}>
        <AppProvider>
          <RouteSwitcher />
          <Routes>
            <Route path="/workspace/:dbId/schema" element={<SchemaEditor />} />
          </Routes>
        </AppProvider>
      </MemoryRouter>
    );

    // Check that initial inventory table and price column are displayed
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /products/i })).toBeDefined();
      expect(screen.getByText('price')).toBeDefined();
    });

    expect(api.getDatabaseSchema).toHaveBeenCalledWith('db_inventory');

    // Trigger navigation to Notes workspace
    await act(async () => {
      fireEvent.click(screen.getByTestId('route-switch-trigger'));
    });

    // Notes table tab and content column should now be loaded
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^notes/i })).toBeDefined();
      expect(screen.getByText('content')).toBeDefined();
    });

    expect(api.getDatabaseSchema).toHaveBeenCalledWith('db_notes');
  });

  it('SchemaEditor ignores stale in-flight response when workspace changes rapidly', async () => {
    let resolveFirstRequest;
    const firstRequestPromise = new Promise((resolve) => {
      resolveFirstRequest = resolve;
    });

    api.getDatabaseSchema.mockImplementation((dbId) => {
      if (dbId === 'db_inventory') {
        return firstRequestPromise;
      }
      return Promise.resolve(mockNotesSchema);
    });

    function TestApp() {
      const navigate = useNavigate();
      return (
        <div>
          <button data-testid="rapid-switch-btn" onClick={() => navigate('/workspace/db_notes/schema')}>
            Switch Route
          </button>
          <Routes>
            <Route path="/workspace/:dbId/schema" element={<SchemaEditor />} />
          </Routes>
        </div>
      );
    }

    render(
      <MemoryRouter initialEntries={['/workspace/db_inventory/schema']}>
        <AppProvider>
          <TestApp />
        </AppProvider>
      </MemoryRouter>
    );

    // db_inventory request is pending; switch immediately to db_notes
    await act(async () => {
      fireEvent.click(screen.getByTestId('rapid-switch-btn'));
    });

    // db_notes resolves immediately
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^notes/i })).toBeDefined();
      expect(screen.getByText('content')).toBeDefined();
    });

    // Now late-resolve db_inventory request
    await act(async () => {
      resolveFirstRequest(mockInventorySchema);
    });

    // Verify notes is STILL displayed and wasn't overwritten by the stale db_inventory response
    expect(screen.getByRole('button', { name: /^notes/i })).toBeDefined();
    expect(screen.queryByRole('button', { name: /products/i })).toBeNull();
  });

  it('Global Refresh button fetches fresh telemetry, gives visual feedback, and notifies views', async () => {
    function ViewWithRefreshCounter() {
      const { refreshCounter } = useApp();
      return <div data-testid="counter">{refreshCounter}</div>;
    }

    render(
      <MemoryRouter initialEntries={['/']}>
        <AppProvider>
          <TopBar />
          <ViewWithRefreshCounter />
        </AppProvider>
      </MemoryRouter>
    );

    // Wait for initial load
    await waitFor(() => {
      expect(screen.getByTestId('counter').textContent).toBe('1');
    });

    const refreshButton = screen.getByRole('button', { name: /refresh application state/i });
    expect(refreshButton).toBeDefined();

    // Click Refresh
    await act(async () => {
      fireEvent.click(refreshButton);
    });

    // Counter increments, triggering active views
    await waitFor(() => {
      expect(screen.getByTestId('counter').textContent).toBe('2');
    });

    // Visual feedback banner is rendered
    expect(screen.getByText(/workspace & system state refreshed/i)).toBeDefined();
  });
});
