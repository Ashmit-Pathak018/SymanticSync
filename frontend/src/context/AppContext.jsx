import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
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

  // Global Refresh & Feedback states
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshFeedback, setRefreshFeedback] = useState(null); // { type: 'success' | 'error', message: string }
  const [refreshCounter, setRefreshCounter] = useState(0);

  // Unsaved changes guard
  const [unsavedChanges, setUnsavedChanges] = useState(false);
  const [unsavedMessage, setUnsavedMessage] = useState('You have unsaved policy edits. Switching workspaces will discard them. Continue?');

  const feedbackTimerRef = useRef(null);

  const refreshState = useCallback(async () => {
    setIsRefreshing(true);
    if (feedbackTimerRef.current) {
      clearTimeout(feedbackTimerRef.current);
    }
    setRefreshFeedback(null);

    try {
      // 1. Health check
      try {
        await api.checkHealth();
        setBackendHealthy(true);
      } catch (hErr) {
        setBackendHealthy(false);
        const failMsg = 'Backend is not reachable on http://127.0.0.1:8000. Run `python main.py`';
        setError(failMsg);
        setRefreshFeedback({ type: 'error', message: failMsg });
        return;
      }

      // 2. Fetch databases, sync status, and policy registry in parallel
      const [dbList, status, registry] = await Promise.allSettled([
        api.getDatabases(),
        api.getSyncStatus(),
        api.getPolicyRegistry(),
      ]);

      if (dbList.status === 'fulfilled') {
        const dbs = Array.isArray(dbList.value) ? dbList.value : [];
        setDatabases(dbs);
        setSelectedDbId((current) => {
          if (current && dbs.some((d) => d.id === current)) {
            return current;
          }
          return dbs.length > 0 ? dbs[0].id : null;
        });
      }

      if (status.status === 'fulfilled') {
        setSyncStatus(status.value);
      }

      if (registry.status === 'fulfilled') {
        setPolicyRegistry(Array.isArray(registry.value) ? registry.value : []);
      }

      setError(null);
      // Increment refresh counter to notify all mounted views to re-fetch
      setRefreshCounter((c) => c + 1);
      setRefreshFeedback({ type: 'success', message: 'Workspace & system state refreshed.' });

      feedbackTimerRef.current = setTimeout(() => {
        setRefreshFeedback(null);
      }, 3500);
    } catch (err) {
      console.error('Error refreshing state:', err);
      setError(err.message);
      setRefreshFeedback({ type: 'error', message: `Refresh failed: ${err.message}` });
      feedbackTimerRef.current = setTimeout(() => {
        setRefreshFeedback(null);
      }, 4000);
    } finally {
      setIsRefreshing(false);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshState();
    // Poll sync status occasionally
    const interval = setInterval(() => {
      api.getSyncStatus()
        .then((st) => setSyncStatus(st))
        .catch(() => {});
    }, 15000);
    return () => {
      clearInterval(interval);
      if (feedbackTimerRef.current) clearTimeout(feedbackTimerRef.current);
    };
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
    isRefreshing,
    refreshFeedback,
    refreshCounter,
    refreshState,
    unsavedChanges,
    setUnsavedChanges,
    unsavedMessage,
    setUnsavedMessage,
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
