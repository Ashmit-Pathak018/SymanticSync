import React, { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Database, RefreshCw, Sparkles, ExternalLink, Activity, CheckCircle, AlertTriangle } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { Button } from '../ui/Button';
import { api } from '../../services/api';

export function TopBar() {
  const location = useLocation();
  const navigate = useNavigate();

  const {
    databases,
    selectedDbId,
    setSelectedDbId,
    backendHealthy,
    refreshState,
    isRefreshing,
    refreshFeedback,
    unsavedChanges,
    setUnsavedChanges,
    unsavedMessage,
  } = useApp();

  const [seeding, setSeeding] = useState(false);
  const [seedSuccess, setSeedSuccess] = useState(null);

  const handleWorkspaceChange = (newDbId) => {
    if (!newDbId || newDbId === selectedDbId) return;

    if (unsavedChanges) {
      const confirmSwitch = window.confirm(
        unsavedMessage || 'You have unsaved changes. Switching workspaces will discard them. Do you want to proceed?'
      );
      if (!confirmSwitch) {
        return;
      }
      setUnsavedChanges(false);
    }

    setSelectedDbId(newDbId);

    // If currently on a workspace-specific subroute, update URL path
    const match = location.pathname.match(/^\/workspace\/[^/]+(\/[^?]*)?$/);
    if (match) {
      const subPath = match[1] || '/schema';
      navigate(`/workspace/${encodeURIComponent(newDbId)}${subPath}`);
    }
  };

  const handleSeed = async (workload) => {
    setSeeding(true);
    setSeedSuccess(null);
    try {
      await api.seedWorkload(workload);
      setSeedSuccess(`Seeded ${workload} workloads!`);
      await refreshState();
      setTimeout(() => setSeedSuccess(null), 3000);
    } catch (err) {
      alert(`Seeding failed: ${err.message}`);
    } finally {
      setSeeding(false);
    }
  };

  return (
    <header className="h-14 bg-white border-b border-border px-6 flex items-center justify-between flex-shrink-0 z-10">
      {/* Left: Active Workspace Selector */}
      <div className="flex items-center gap-3">
        <label htmlFor="workspace-select" className="text-xs font-semibold text-text-secondary flex items-center gap-1.5 uppercase tracking-wider">
          <Database className="w-3.5 h-3.5 text-primary" />
          <span>Workspace:</span>
        </label>
        <select
          id="workspace-select"
          aria-label="Active Workspace"
          value={selectedDbId || ''}
          onChange={(e) => handleWorkspaceChange(e.target.value)}
          className="text-xs font-medium bg-gray-50 border border-border rounded-md px-3 py-1.5 text-text-primary focus:outline-hidden focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all cursor-pointer"
        >
          {databases.length === 0 ? (
            <option value="">No databases registered</option>
          ) : (
            databases.map((db) => (
              <option key={db.id} value={db.id}>
                {db.name} ({db.table_count} {db.table_count === 1 ? 'table' : 'tables'})
              </option>
            ))
          )}
        </select>

        {seedSuccess && (
          <span className="text-xs text-success bg-success-light px-2 py-0.5 rounded-sm font-medium animate-fade-in flex items-center gap-1">
            <CheckCircle className="w-3.5 h-3.5" />
            <span>{seedSuccess}</span>
          </span>
        )}

        {/* Global Refresh Feedback Toast */}
        {refreshFeedback && (
          <span
            className={`text-xs px-2.5 py-0.5 rounded-sm font-medium animate-fade-in flex items-center gap-1.5 transition-all ${
              refreshFeedback.type === 'success'
                ? 'bg-success-light text-success border border-success/30'
                : 'bg-danger-light text-danger border border-danger/30'
            }`}
          >
            {refreshFeedback.type === 'success' ? (
              <CheckCircle className="w-3.5 h-3.5" />
            ) : (
              <AlertTriangle className="w-3.5 h-3.5" />
            )}
            <span>{refreshFeedback.message}</span>
          </span>
        )}
      </div>

      {/* Right: Actions, Health, Docs */}
      <div className="flex items-center gap-3">
        {/* Quick Seeder Dropdown */}
        <div className="relative group">
          <Button
            size="sm"
            variant="secondary"
            icon={Sparkles}
            loading={seeding}
            title="Seed sample workloads with preconfigured conflicts"
          >
            Seed Workloads
          </Button>
          <div className="absolute right-0 mt-1 w-44 bg-white border border-border rounded-lg shadow-lg py-1.5 hidden group-hover:block z-30">
            <button
              onClick={() => handleSeed('all')}
              className="w-full text-left px-3 py-1.5 text-xs text-text-primary hover:bg-gray-50 flex items-center justify-between"
            >
              <span>Seed All (3 Workloads)</span>
              <span className="text-[10px] bg-primary-light text-primary px-1 rounded-sm">All</span>
            </button>
            <button
              onClick={() => handleSeed('inventory')}
              className="w-full text-left px-3 py-1.5 text-xs text-text-primary hover:bg-gray-50"
            >
              Inventory (Stock & Prices)
            </button>
            <button
              onClick={() => handleSeed('notes')}
              className="w-full text-left px-3 py-1.5 text-xs text-text-primary hover:bg-gray-50"
            >
              Notes (Appends & Edits)
            </button>
            <button
              onClick={() => handleSeed('health')}
              className="w-full text-left px-3 py-1.5 text-xs text-text-primary hover:bg-gray-50"
            >
              Healthcare (Dosages & Blood)
            </button>
          </div>
        </div>

        {/* Global Refresh Button */}
        <Button
          size="sm"
          variant="ghost"
          icon={RefreshCw}
          loading={isRefreshing}
          disabled={isRefreshing}
          onClick={() => refreshState()}
          title="Refresh server telemetry and active view data"
          aria-label="Refresh application state"
        >
          {isRefreshing ? 'Refreshing...' : 'Refresh'}
        </Button>

        {/* API Health Pill */}
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
            backendHealthy
              ? 'bg-[#EAF7F0] text-[#2D9B62] border-[#2D9B62]/30'
              : 'bg-[#FDF2F3] text-[#D94B5B] border-[#D94B5B]/30'
          }`}
          title={backendHealthy ? 'FastAPI Backend Healthy at 127.0.0.1:8000' : 'Backend Unreachable'}
        >
          <span
            className={`w-2 h-2 rounded-full ${
              backendHealthy ? 'bg-[#2D9B62] animate-pulse' : 'bg-[#D94B5B]'
            }`}
          />
          <span>{backendHealthy ? 'API Active' : 'API Offline'}</span>
        </div>

        {/* Swagger Docs Link */}
        <a
          href="http://127.0.0.1:8000/docs"
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-text-secondary hover:text-primary flex items-center gap-1 font-medium transition-colors ml-1"
          title="Open FastAPI Swagger Documentation"
        >
          <Activity className="w-3.5 h-3.5" />
          <span>Swagger</span>
          <ExternalLink className="w-3 h-3 text-text-muted" />
        </a>
      </div>
    </header>
  );
}
