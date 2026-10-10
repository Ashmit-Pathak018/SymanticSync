import React from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { useApp } from '../../context/AppContext';
import { Alert } from '../ui/Alert';

export function Layout() {
  const { error, backendHealthy } = useApp();

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-workspace">
      {/* Persistent Left Sidebar */}
      <Sidebar />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Header */}
        <TopBar />

        {/* Global Connection Warning */}
        {backendHealthy === false && (
          <div className="p-4 bg-danger-light border-b border-danger/30">
            <Alert variant="danger" title="Cannot connect to SemanticSync API Server">
              The backend API server at <code className="bg-white/80 px-1 py-0.5 rounded font-mono">http://127.0.0.1:8000</code> is unreachable.
              Please start it using <code className="bg-white/80 px-1 py-0.5 rounded font-mono">python main.py</code> in your project directory.
            </Alert>
          </div>
        )}

        {/* View Content with Scrolling */}
        <main className="flex-1 overflow-y-auto p-6 md:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
