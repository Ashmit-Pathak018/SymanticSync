import React, { useState, useEffect } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import {
  Terminal,
  Play,
  RotateCcw,
  Sparkles,
  History,
  Clock,
  Database,
  GitBranch,
  ShieldAlert,
  CheckCircle2,
  AlertCircle,
  Copy,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Alert } from '../components/ui/Alert';
import { api } from '../services/api';

const SAMPLE_QUERIES = [
  'SELECT * FROM products;',
  'SELECT id, sku, quantity, price, description FROM products;',
  'SELECT * FROM notes;',
  'SELECT * FROM patients;',
  'PRAGMA table_info(products);',
];

export function SqlConsole() {
  const { dbId } = useParams();
  const [searchParams] = useSearchParams();
  const { databases, selectedDbId, setSelectedDbId, refreshCounter } = useApp();

  const [replicas, setReplicas] = useState([]);
  const [selectedTarget, setSelectedTarget] = useState('base'); // 'base' or replica_id
  const [sql, setSql] = useState('SELECT * FROM products LIMIT 50;');
  const [allowWrite, setAllowWrite] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);

  const replicaRequestIdRef = React.useRef(0);

  useEffect(() => {
    if (dbId && dbId !== selectedDbId) {
      setSelectedDbId(dbId);
    }
  }, [dbId, selectedDbId, setSelectedDbId]);

  // Clear previous query results when switching databases
  useEffect(() => {
    setResult(null);
    setError(null);
    setSelectedTarget('base');
  }, [dbId]);

  // Load replicas for this DB whenever dbId or refreshCounter changes
  useEffect(() => {
    async function loadReplicas() {
      if (!dbId) return;
      const reqId = ++replicaRequestIdRef.current;
      try {
        const reps = await api.getReplicas(dbId);
        if (reqId !== replicaRequestIdRef.current) return;
        const repList = Array.isArray(reps) ? reps : [];
        setReplicas(repList);

        // Check URL query param for replica
        const repParam = searchParams.get('replica');
        if (repParam && repList.some((r) => r.replica_id === repParam)) {
          setSelectedTarget(repParam);
        } else {
          setSelectedTarget('base');
        }
      } catch (err) {
        if (reqId === replicaRequestIdRef.current) {
          console.error('Failed to load replicas:', err);
        }
      }
    }
    loadReplicas();
  }, [dbId, searchParams, refreshCounter]);

  // Load history from localStorage
  useEffect(() => {
    const saved = localStorage.getItem('semanticsync_sql_history');
    if (saved) {
      try {
        setHistory(JSON.parse(saved));
      } catch {}
    }
  }, []);

  const saveToHistory = (query) => {
    const trimmed = query.trim();
    if (!trimmed) return;
    const next = [trimmed, ...history.filter((h) => h !== trimmed)].slice(0, 20);
    setHistory(next);
    localStorage.setItem('semanticsync_sql_history', JSON.stringify(next));
  };

  const handleExecute = async () => {
    if (!sql.trim()) return;
    setExecuting(true);
    setError(null);
    setResult(null);

    const replicaId = selectedTarget === 'base' ? null : selectedTarget;

    try {
      const res = await api.executeQuery(dbId, sql.trim(), replicaId, allowWrite);
      setResult(res);
      saveToHistory(sql);
    } catch (err) {
      setError(err.data?.detail || err.message);
    } finally {
      setExecuting(false);
    }
  };

  // Keyboard shortcut Ctrl+Enter / Cmd+Enter
  const handleKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleExecute();
    }
  };

  const formatSql = () => {
    const keywords = ['SELECT', 'FROM', 'WHERE', 'INSERT INTO', 'VALUES', 'UPDATE', 'SET', 'DELETE FROM', 'ORDER BY', 'GROUP BY', 'LIMIT', 'JOIN', 'LEFT JOIN', 'INNER JOIN', 'AND', 'OR', 'PRAGMA'];
    let formatted = sql;
    keywords.forEach((kw) => {
      const regex = new RegExp(`\\b${kw}\\b`, 'gi');
      formatted = formatted.replace(regex, kw);
    });
    setSql(formatted);
  };

  const currentDb = databases.find((d) => d.id === dbId);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-primary bg-primary-light px-2 py-0.5 rounded-sm">
              {dbId}
            </span>
            <span className="text-xs text-text-muted">/</span>
            <span className="text-xs font-semibold text-text-secondary">Interactive SQLite Console</span>
          </div>
          <h1 className="text-xl font-bold text-text-primary mt-1">
            SQL Query & State Inspector
          </h1>
          <p className="text-xs text-text-secondary mt-0.5">
            Execute standard SQL directly against the base database or individual offline replicas to observe convergence.
          </p>
        </div>

        {/* Target Selector */}
        <div className="flex items-center gap-2 bg-white border border-border rounded-lg p-1.5 shadow-xs">
          <label className="text-xs font-semibold text-text-secondary flex items-center gap-1 pl-2">
            {selectedTarget === 'base' ? (
              <Database className="w-3.5 h-3.5 text-primary" />
            ) : (
              <GitBranch className="w-3.5 h-3.5 text-success" />
            )}
            <span>Target:</span>
          </label>
          <select
            value={selectedTarget}
            onChange={(e) => setSelectedTarget(e.target.value)}
            className="text-xs font-mono font-medium bg-gray-50 border border-border rounded-md px-2.5 py-1.5 text-text-primary focus:ring-1 focus:ring-primary focus:outline-hidden"
          >
            <option value="base">Base SQLite Database</option>
            {replicas.map((r) => (
              <option key={r.replica_id} value={r.replica_id}>
                Replica: {r.replica_id}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Editor & Controls */}
      <Card className="p-0 overflow-hidden">
        {/* Editor Toolbar */}
        <div className="px-4 py-2.5 bg-gray-50 border-b border-border flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-3">
            <span className="font-mono text-text-secondary font-medium">SQLite 3</span>
            <span className="text-text-muted">|</span>
            <span className="text-text-muted">
              Press <kbd className="px-1.5 py-0.5 bg-white border border-border rounded text-[10px] font-mono shadow-2xs">Ctrl + Enter</kbd> to execute
            </span>
          </div>

          <div className="flex items-center gap-2">
            {selectedTarget === 'base' && (
              <label className="flex items-center gap-1.5 text-xs text-text-secondary cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={allowWrite}
                  onChange={(e) => setAllowWrite(e.target.checked)}
                  className="rounded border-border text-primary focus:ring-primary w-3.5 h-3.5"
                />
                <span className="text-[11px]">Allow Base DB Writes</span>
              </label>
            )}

            <button
              onClick={formatSql}
              className="px-2 py-1 hover:bg-white rounded border border-transparent hover:border-border text-text-secondary text-xs transition-colors"
            >
              Format SQL
            </button>
            <button
              onClick={() => setSql('')}
              className="px-2 py-1 hover:bg-white rounded border border-transparent hover:border-border text-text-secondary text-xs transition-colors"
            >
              Clear
            </button>
          </div>
        </div>

        {/* Text Area */}
        <div className="relative">
          <textarea
            value={sql}
            onChange={(e) => setSql(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={5}
            spellCheck={false}
            className="w-full p-4 font-mono text-xs text-text-primary bg-white focus:outline-hidden leading-relaxed resize-y border-none"
            placeholder="Write standard SQLite SQL statements here..."
          />
        </div>

        {/* Bottom Bar: Quick templates & Run button */}
        <div className="px-4 py-2.5 bg-gray-50/70 border-t border-border flex flex-wrap items-center justify-between gap-2">
          {/* Quick Query Templates */}
          <div className="flex items-center gap-1.5 overflow-x-auto">
            <span className="text-[11px] font-semibold text-text-muted uppercase">Templates:</span>
            {SAMPLE_QUERIES.map((sq, i) => (
              <button
                key={i}
                onClick={() => setSql(sq)}
                className="text-[11px] font-mono bg-white hover:bg-primary-light hover:text-primary px-2 py-0.5 rounded border border-border/80 text-text-secondary truncate max-w-[200px] transition-colors"
                title={sq}
              >
                {sq}
              </button>
            ))}
          </div>

          <Button
            variant="primary"
            size="sm"
            icon={Play}
            loading={executing}
            onClick={handleExecute}
          >
            Run Query
          </Button>
        </div>
      </Card>

      {/* Query Error Alert */}
      {error && (
        <Alert variant="danger" title="SQL Execution Error">
          <div className="font-mono text-xs mt-1">{error}</div>
          {selectedTarget === 'base' && error.includes('allow_write') && (
            <p className="mt-2 text-xs text-text-secondary">
              Safety rule: To prevent unintentional changes to the base schema, check the "Allow Base DB Writes" checkbox above before running non-SELECT statements.
            </p>
          )}
        </Alert>
      )}

      {/* Query Results */}
      {result && (
        <Card className="p-0 overflow-hidden" title="Query Results">
          <div className="px-5 py-2.5 bg-gray-50 border-b border-border flex items-center justify-between text-xs text-text-secondary">
            <div className="flex items-center gap-3">
              <span className="font-semibold text-text-primary">
                {result.row_count} {result.row_count === 1 ? 'row' : 'rows'} returned
              </span>
              <span className="text-text-muted">|</span>
              <span className="flex items-center gap-1 font-mono text-[11px]">
                <Clock className="w-3.5 h-3.5 text-text-muted" />
                {result.duration_ms.toFixed(2)} ms
              </span>
            </div>
            <span className="font-mono text-[11px] text-text-muted">
              Target: {selectedTarget === 'base' ? 'Base Database' : selectedTarget}
            </span>
          </div>

          {result.rows.length === 0 ? (
            <div className="p-8 text-center text-xs text-text-muted">
              Query completed with 0 rows returned.
            </div>
          ) : (
            <div className="overflow-x-auto max-h-96 overflow-y-auto">
              <table className="w-full text-left text-xs border-collapse font-mono">
                <thead>
                  <tr className="bg-gray-100/70 border-b border-border sticky top-0 z-10">
                    {result.columns.map((col, idx) => (
                      <th key={idx} className="py-2.5 px-4 font-semibold text-text-primary whitespace-nowrap">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {result.rows.map((row, rIdx) => (
                    <tr key={rIdx} className="hover:bg-gray-50 transition-colors">
                      {row.map((val, cIdx) => (
                        <td key={cIdx} className="py-2 px-4 whitespace-nowrap text-text-primary">
                          {val === null ? (
                            <span className="text-text-muted italic font-sans text-[11px]">NULL</span>
                          ) : typeof val === 'object' ? (
                            JSON.stringify(val)
                          ) : (
                            String(val)
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {/* Query History */}
      {history.length > 0 && (
        <Card className="p-4" title="Recent Queries">
          <div className="flex flex-wrap gap-2">
            {history.slice(0, 8).map((h, i) => (
              <button
                key={i}
                onClick={() => setSql(h)}
                className="text-xs font-mono bg-gray-50 hover:bg-gray-100 border border-border px-2.5 py-1 rounded text-text-secondary hover:text-text-primary transition-colors truncate max-w-sm"
                title={h}
              >
                {h}
              </button>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
