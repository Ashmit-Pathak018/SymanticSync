import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Database,
  Layers,
  Terminal,
  Zap,
  RefreshCw,
  BarChart3,
  BookOpen,
  GitBranch,
} from 'lucide-react';
import { useApp } from '../../context/AppContext';

export function Sidebar() {
  const { selectedDb, syncStatus } = useApp();
  const dbId = selectedDb?.id;

  const pendingCount = (syncStatus?.pending_conflicts || 0) + (syncStatus?.flagged_conflicts || 0);

  const mainNav = [
    { to: '/', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/databases', label: 'Workspaces', icon: Database },
  ];

  const workspaceNav = dbId
    ? [
        { to: `/workspace/${dbId}/schema`, label: 'Schema Policies', icon: Layers },
        { to: `/workspace/${dbId}/sql`, label: 'SQL Console', icon: Terminal },
        { to: `/workspace/${dbId}/replicas`, label: 'Replicas', icon: GitBranch },
      ]
    : [];

  const systemNav = [
    {
      to: '/conflicts',
      label: 'Conflicts',
      icon: Zap,
      badge: pendingCount > 0 ? pendingCount : null,
      badgeVariant: syncStatus?.flagged_conflicts > 0 ? 'bg-danger text-white' : 'bg-warning text-white',
    },
    { to: '/sync', label: 'CRDT Sync Hub', icon: RefreshCw },
    { to: '/benchmark', label: 'Research Benchmark', icon: BarChart3 },
    { to: '/settings', label: 'Policy Registry', icon: BookOpen },
  ];

  return (
    <aside className="w-56 bg-nav text-text-inverse flex flex-col flex-shrink-0 select-none shadow-md z-20 min-h-screen">
      {/* Brand Header */}
      <div className="h-14 px-4 flex items-center gap-3 border-b border-white/10">
        <img src="/logo.svg" alt="SemanticSync" className="w-7 h-7" />
        <div className="flex flex-col">
          <span className="font-bold text-sm tracking-tight text-white leading-tight">SemanticSync</span>
          <span className="text-[10px] text-gray-400 font-mono tracking-wider">STUDIO v1.0</span>
        </div>
      </div>

      {/* Navigation List */}
      <div className="flex-1 px-2.5 py-4 space-y-6 overflow-y-auto">
        {/* Main Section */}
        <div>
          <div className="px-2.5 mb-1.5 text-[10px] font-semibold text-gray-400 tracking-wider uppercase">
            Platform
          </div>
          <nav className="space-y-0.5">
            {mainNav.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    `flex items-center gap-2.5 px-2.5 py-2 rounded-md text-xs font-medium transition-colors ${
                      isActive
                        ? 'bg-primary text-white shadow-xs'
                        : 'text-gray-300 hover:text-white hover:bg-white/5'
                    }`
                  }
                >
                  <Icon className="w-4 h-4 flex-shrink-0" />
                  <span>{item.label}</span>
                </NavLink>
              );
            })}
          </nav>
        </div>

        {/* Selected Workspace Nav */}
        {workspaceNav.length > 0 && (
          <div>
            <div className="px-2.5 mb-1.5 flex items-center justify-between text-[10px] font-semibold text-gray-400 tracking-wider uppercase">
              <span>Active Workspace</span>
              <span className="text-[9px] text-primary bg-primary/20 px-1.5 py-0.2 rounded font-mono truncate max-w-[80px]">
                {selectedDb.name}
              </span>
            </div>
            <nav className="space-y-0.5">
              {workspaceNav.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      `flex items-center gap-2.5 px-2.5 py-2 rounded-md text-xs font-medium transition-colors ${
                        isActive
                          ? 'bg-primary text-white shadow-xs'
                          : 'text-gray-300 hover:text-white hover:bg-white/5'
                      }`
                    }
                  >
                    <Icon className="w-4 h-4 flex-shrink-0" />
                    <span>{item.label}</span>
                  </NavLink>
                );
              })}
            </nav>
          </div>
        )}

        {/* Middleware & Sync Section */}
        <div>
          <div className="px-2.5 mb-1.5 text-[10px] font-semibold text-gray-400 tracking-wider uppercase">
            Middleware & Sync
          </div>
          <nav className="space-y-0.5">
            {systemNav.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `flex items-center justify-between px-2.5 py-2 rounded-md text-xs font-medium transition-colors ${
                      isActive
                        ? 'bg-primary text-white shadow-xs'
                        : 'text-gray-300 hover:text-white hover:bg-white/5'
                    }`
                  }
                >
                  <div className="flex items-center gap-2.5">
                    <Icon className="w-4 h-4 flex-shrink-0" />
                    <span>{item.label}</span>
                  </div>
                  {item.badge !== null && item.badge !== undefined && (
                    <span
                      className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded-full ${item.badgeVariant}`}
                    >
                      {item.badge}
                    </span>
                  )}
                </NavLink>
              );
            })}
          </nav>
        </div>
      </div>

      {/* Footer status / principle reminder */}
      <div className="p-3 bg-[#0B1126] border-t border-white/5 text-[11px] text-gray-400">
        <p className="font-semibold text-gray-300">Core Principle:</p>
        <p className="text-[10px] text-gray-400 mt-0.5 leading-snug italic">
          "CRDT handles convergence; semantic middleware handles conflict meaning."
        </p>
      </div>
    </aside>
  );
}
