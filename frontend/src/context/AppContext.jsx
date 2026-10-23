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

  const clearWorkspaceState = useCallback(() => {
    setDatabases([]);
    setSelectedDbId(null);
    setSyncStatus(null);
    setPolicyRegistry([]);
    setRefreshCounter((current) => current + 1);
  }, []);

  const refreshState = useCallback(async () => {
    setIsRefreshing(true);
    if (feedbackTimerRef.current) {
      clearTimeout(feedbackTimerRef.current);
    }
    setRefreshFeedback(null);
    setError(null);

    try {
      // 1. Health check
      try {
        await api.checkHealth();
        setBackendHealthy(true);
      } catch {
        setBackendHealthy(false);
        const failMsg = 'Backend API is unavailable. Start it with `python main.py` and check the configured API URL.';
        clearWorkspaceState();
        setError(failMsg);
        setRefreshFeedback({ type: 'error', message: failMsg });
        return false;
      }

      // 2. Fetch databases, sync status, and policy registry in parallel
      const [dbList, status, registry] = await Promise.allSettled([
        api.getDatabases(),
        api.getSyncStatus(),
        api.getPolicyRegistry(),
      ]);

      const failedResources = [];
      if (dbList.status === 'fulfilled') {
        const dbs = Array.isArray(dbList.value) ? dbList.value : [];
        setDatabases(dbs);
        setSelectedDbId((current) => {
          if (current && dbs.some((d) => d.id === current)) {
            return current;
          }
          return dbs.length > 0 ? dbs[0].id : null;
        });
      } else {
        setDatabases([]);
        setSelectedDbId(null);
        failedResources.push(`workspaces: ${dbList.reason?.message || 'request failed'}`);
      }

      if (status.status === 'fulfilled') {
        setSyncStatus(status.value);
      } else {
        setSyncStatus(null);
        failedResources.push(`sync status: ${status.reason?.message || 'request failed'}`);
      }

      if (registry.status === 'fulfilled') {
        setPolicyRegistry(Array.isArray(registry.value) ? registry.value : []);
      } else {
        setPolicyRegistry([]);
        failedResources.push(`policy catalog: ${registry.reason?.message || 'request failed'}`);
      }

      // Increment refresh counter to notify all mounted views to re-fetch
      setRefreshCounter((c) => c + 1);
      if (failedResources.length) {
        const message = `Some live data could not be refreshed (${failedResources.join('; ')}). Retry after checking the API.`;
        setError(message);
        setRefreshFeedback({ type: 'error', message });
        return false;
      }
      setError(null);
      setRefreshFeedback({ type: 'success', message: 'Workspace & system state refreshed.' });

      feedbackTimerRef.current = setTimeout(() => {
        setRefreshFeedback(null);
      }, 3500);
    } catch (err) {
      console.error('Error refreshing state:', err);
      setError(err.message);
      setRefreshFeedback({ type: 'error', message: `Refresh failed: ${err.message}` });
      return false;
    } finally {
      setIsRefreshing(false);
      setLoading(false);
    }
  }, [clearWorkspaceState]);

  useEffect(() => {
    refreshState();
    // Poll sync status occasionally
    const interval = setInterval(() => {
      api.getSyncStatus().then((st) => {
        setBackendHealthy(true);
        setSyncStatus(st);
      }).catch((pollError) => {
        setBackendHealthy(false);
        clearWorkspaceState();
        const message = 'Sync status is unavailable. Start the backend with `python main.py`, then refresh.';
        setError(message);
        setRefreshFeedback({ type: 'error', message: pollError.message || message });
      });
    }, 15000);
    return () => {
      clearInterval(interval);
      if (feedbackTimerRef.current) clearTimeout(feedbackTimerRef.current);
    };
  }, [refreshState, clearWorkspaceState]);

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
