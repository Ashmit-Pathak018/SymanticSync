import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';

const AppContext = createContext(null);

export function AppProvider({ children }) {
  const [databases, setDatabases] = useState([]);
  const [selectedDbId, setSelectedDbId] = useState(null);
  const [syncStatus, setSyncStatus] = useState(null);
  const [policyRegistry, setPolicyRegistry] = useState([]);
  const [backendHealthy, setBackendHealthy] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const refreshState = useCallback(async () => {
    try {
      // 1. Health check
      try {
        await api.checkHealth();
        setBackendHealthy(true);
      } catch (hErr) {
        setBackendHealthy(false);
        setError('Backend is not reachable on http://127.0.0.1:8000. Run `python main.py`');
        return;
      }

      // 2. Fetch databases and sync status in parallel
      const [dbList, status, registry] = await Promise.allSettled([
        api.getDatabases(),
        api.getSyncStatus(),
        api.getPolicyRegistry(),
      ]);

      if (dbList.status === 'fulfilled') {
        const dbs = Array.isArray(dbList.value) ? dbList.value : [];
        setDatabases(dbs);
        if (dbs.length > 0 && !selectedDbId) {
          setSelectedDbId(dbs[0].id);
        }
      }

      if (status.status === 'fulfilled') {
        setSyncStatus(status.value);
      }

      if (registry.status === 'fulfilled') {
        setPolicyRegistry(Array.isArray(registry.value) ? registry.value : []);
      }

      setError(null);
    } catch (err) {
      console.error('Error refreshing state:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [selectedDbId]);

  useEffect(() => {
    refreshState();
    // Poll sync status occasionally
    const interval = setInterval(() => {
      api.getSyncStatus()
        .then((st) => setSyncStatus(st))
        .catch(() => {});
    }, 15000);
    return () => clearInterval(interval);
  }, [refreshState]);

  const selectedDb = databases.find((d) => d.id === selectedDbId) || databases[0] || null;

  const value = {
    databases,
    selectedDbId,
    setSelectedDbId,
    selectedDb,
    syncStatus,
    policyRegistry,
    backendHealthy,
    loading,
    error,
    refreshState,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useApp must be used within an AppProvider');
  }
  return context;
}
