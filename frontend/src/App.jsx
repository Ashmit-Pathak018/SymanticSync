import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider } from './context/AppContext';
import { Layout } from './components/layout/Layout';

import { Dashboard } from './views/Dashboard';
import { Databases } from './views/Databases';
import { SchemaEditor } from './views/SchemaEditor';
import { SqlConsole } from './views/SqlConsole';
import { ReplicaManager } from './views/ReplicaManager';
import { Conflicts } from './views/Conflicts';
import { SyncHub } from './views/SyncHub';
import { Analytics } from './views/Analytics';
import { Settings } from './views/Settings';

export default function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/databases" element={<Databases />} />
            <Route path="/workspace/:dbId/schema" element={<SchemaEditor />} />
            <Route path="/workspace/:dbId/sql" element={<SqlConsole />} />
            <Route path="/workspace/:dbId/replicas" element={<ReplicaManager />} />
            <Route path="/conflicts" element={<Conflicts />} />
            <Route path="/sync" element={<SyncHub />} />
            <Route path="/benchmark" element={<Analytics />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </AppProvider>
    </BrowserRouter>
  );
}
