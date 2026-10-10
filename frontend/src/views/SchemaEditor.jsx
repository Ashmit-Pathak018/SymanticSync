import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Layers,
  Save,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Key,
  Info,
  ShieldCheck,
  ShieldAlert,
  Loader2,
  Database,
  ArrowRight,
  RefreshCw,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Alert } from '../components/ui/Alert';
import { api } from '../services/api';

const POLICIES = ['SUM', 'AVG', 'APPEND', 'LWW', 'REJECT', 'MIN', 'MAX'];

export function SchemaEditor() {
  const { dbId } = useParams();
  const navigate = useNavigate();
  const {
    databases,
    selectedDbId,
    setSelectedDbId,
    refreshCounter,
    setUnsavedChanges,
    setUnsavedMessage,
  } = useApp();

  const [loading, setLoading] = useState(true);
  const [schemaData, setSchemaData] = useState(null);
  const [activeTable, setActiveTable] = useState('');
  const [policyAssignments, setPolicyAssignments] = useState({}); // `${table}:${col}` -> policy
  const [validationStates, setValidationStates] = useState({});   // `${table}:${col}` -> { valid, error_code, error_message }
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(null);
  const [generalError, setGeneralError] = useState(null);

  // Request race-condition guard and dirty state tracker
  const requestIdRef = useRef(0);
  const initialPoliciesRef = useRef({});

  // Sync selectedDbId with route param if different
  useEffect(() => {
    if (dbId && dbId !== selectedDbId) {
      setSelectedDbId(dbId);
    }
  }, [dbId, selectedDbId, setSelectedDbId]);

  // Configure unsaved changes message
  useEffect(() => {
    setUnsavedMessage(`You have unsaved policy changes for workspace '${dbId}'. Switching workspaces will discard them. Do you want to proceed?`);
    return () => {
      setUnsavedChanges(false);
    };
  }, [dbId, setUnsavedChanges, setUnsavedMessage]);

  // Load schema and active policies
  const loadSchema = useCallback(async () => {
    if (!dbId) return;

    const reqId = ++requestIdRef.current;
    setLoading(true);
    setGeneralError(null);
    setSaveSuccess(null);
    // Immediately clear previous workspace data to prevent stale display
    setSchemaData(null);
    setPolicyAssignments({});
    setValidationStates({});

    try {
      const schema = await api.getDatabaseSchema(dbId);
      // Discard stale response if a newer request was initiated
      if (reqId !== requestIdRef.current) return;

      const initialAssignments = {};
      const initialValidations = {};
      const validationTasks = [];

      for (const tbl of schema.tables || []) {
        for (const col of tbl.columns || []) {
          const key = `${tbl.table_name}:${col.name}`;
          const pol = col.policy || 'LWW';
          initialAssignments[key] = pol;

          if (col.is_pk) {
            initialValidations[key] = { valid: true, error_message: null };
          } else {
            validationTasks.push({
              key,
              table: tbl.table_name,
              column: col.name,
              policy: pol,
              normalized_type: col.normalized_type,
            });
          }
        }
      }

      // Concurrently validate all non-PK column policies
      const validationResults = await Promise.all(
        validationTasks.map(async (task) => {
          try {
            const res = await api.validatePolicy({
              table: task.table,
              column: task.column,
              policy: task.policy,
              normalized_type: task.normalized_type,
            });
            return [task.key, res];
          } catch (err) {
            return [
              task.key,
              { valid: false, error_message: err.data?.detail || err.message },
            ];
          }
        })
      );

      // Discard if superseded during validation calls
      if (reqId !== requestIdRef.current) return;

      for (const [key, res] of validationResults) {
        initialValidations[key] = res;
      }

      initialPoliciesRef.current = { ...initialAssignments };
      setUnsavedChanges(false);
      setSchemaData(schema);
      setPolicyAssignments(initialAssignments);
      setValidationStates(initialValidations);

      setActiveTable((prevTable) => {
        if (prevTable && schema.tables?.some((t) => t.table_name === prevTable)) {
          return prevTable;
        }
        return schema.tables?.[0]?.table_name || '';
      });
    } catch (err) {
      if (reqId === requestIdRef.current) {
        console.error('Failed to load schema:', err);
        setGeneralError(err.data?.detail || err.message);
      }
    } finally {
      if (reqId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [dbId, setUnsavedChanges]);

  // Reload when dbId changes OR when global refreshCounter increments
  useEffect(() => {
    loadSchema();
  }, [loadSchema, refreshCounter]);

  const handlePolicyChange = async (tableName, col, newPolicy) => {
    const key = `${tableName}:${col.name}`;
    const nextAssignments = { ...policyAssignments, [key]: newPolicy };
    setPolicyAssignments(nextAssignments);

    // Track whether user has unsaved edits
    const isDirty = Object.keys(nextAssignments).some(
      (k) => nextAssignments[k] !== initialPoliciesRef.current[k]
    );
    setUnsavedChanges(isDirty);

    // Immediate fail-fast Policy Validator call
    try {
      const res = await api.validatePolicy({
        table: tableName,
        column: col.name,
        policy: newPolicy,
        normalized_type: col.normalized_type,
      });
      setValidationStates((prev) => ({ ...prev, [key]: res }));
    } catch (err) {
      setValidationStates((prev) => ({
        ...prev,
        [key]: {
          valid: false,
          error_code: 'VALIDATION_FAILED',
          error_message: err.data?.detail || err.message,
        },
      }));
    }
  };

  // Check if any column in current schema is invalid
  const hasInvalidPolicies = Object.values(validationStates).some((v) => v && v.valid === false);

  const handleSaveAll = async () => {
    if (hasInvalidPolicies) return;
    setSaving(true);
    setSaveSuccess(null);
    setGeneralError(null);

    try {
      // Build batch assignments payload for the active table
      const assignments = [];
      if (currentTable) {
        for (const col of currentTable.columns) {
          if (!col.is_pk) {
            const key = `${effectiveActiveTable}:${col.name}`;
            const pol = policyAssignments[key] || 'LWW';
            assignments.push({
              table: effectiveActiveTable,
              column: col.name,
              policy: pol,
            });
          }
        }
      }

      await api.setPolicies(dbId, assignments);

      // Update initial baseline
      assignments.forEach((a) => {
        initialPoliciesRef.current[`${a.table}:${a.column}`] = a.policy;
      });

      const isStillDirty = Object.keys(policyAssignments).some(
        (k) => policyAssignments[k] !== initialPoliciesRef.current[k]
      );
      setUnsavedChanges(isStillDirty);

      setSaveSuccess(`Policies for table '${effectiveActiveTable}' successfully updated!`);
      setTimeout(() => setSaveSuccess(null), 4000);
    } catch (err) {
      setGeneralError(err.data?.detail || err.message);
    } finally {
      setSaving(false);
    }
  };

  const currentDb = databases.find((d) => d.id === dbId);
  const currentTable =
    schemaData?.tables?.find((t) => t.table_name === activeTable) ||
    schemaData?.tables?.[0] ||
    null;
  const effectiveActiveTable = currentTable?.table_name || activeTable;

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-text-secondary">
        <Loader2 className="w-8 h-8 animate-spin text-primary mb-3" />
        <p className="text-sm font-medium">Inspecting SQLite PRAGMA table definitions for '{dbId}'...</p>
        <span className="text-xs text-text-muted mt-1">Reading column types, constraints, and assigned policies</span>
      </div>
    );
  }

  if (generalError && !schemaData) {
    return (
      <div className="max-w-2xl mx-auto py-10 space-y-4">
        <Alert variant="danger" title="Schema Inspection Error">
          {generalError}
        </Alert>
        <div className="flex items-center gap-3">
          <Button variant="primary" size="sm" icon={RefreshCw} onClick={loadSchema}>
            Retry Load
          </Button>
          <Button variant="secondary" size="sm" onClick={() => navigate('/databases')}>
            Back to Workspaces
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-primary bg-primary-light px-2 py-0.5 rounded-sm font-semibold">
              {currentDb?.name || dbId}
            </span>
            <span className="text-xs text-text-muted">/</span>
            <span className="text-xs font-semibold text-text-secondary">Policy Designer</span>
          </div>
          <h1 className="text-xl font-bold text-text-primary mt-1">
            Schema & Semantic Policy Designer
          </h1>
          <p className="text-xs text-text-secondary mt-0.5">
            Assign attribute-level merge policies to guide how divergent concurrent updates reconcile.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            icon={RotateCcw}
            onClick={loadSchema}
            title="Reload schema and active policies from database"
          >
            Reload Schema
          </Button>
          <Button
            variant="primary"
            icon={Save}
            loading={saving}
            disabled={hasInvalidPolicies}
            onClick={handleSaveAll}
            title={hasInvalidPolicies ? 'Fix incompatible policies before saving' : 'Save policy assignments'}
          >
            Save Table Policies
          </Button>
        </div>
      </div>

      {saveSuccess && (
        <Alert variant="success" title="Policy Assignments Updated">
          {saveSuccess}
        </Alert>
      )}

      {hasInvalidPolicies && (
        <Alert variant="danger" title="Incompatible Merge Policies Detected">
          One or more columns have policy assignments incompatible with their SQLite datatype.
          SemanticSync fails fast to prevent runtime corruption. Please correct the highlighted assignments before saving.
        </Alert>
      )}

      {generalError && (
        <Alert variant="danger" title="Operation Error">
          {generalError}
        </Alert>
      )}

      {/* Table Selector Tabs */}
      <div className="flex items-center gap-2 border-b border-border pb-1 overflow-x-auto">
        <span className="text-xs font-semibold text-text-secondary mr-2 uppercase tracking-wider">
          Tables:
        </span>
        {schemaData?.tables?.map((tbl) => (
          <button
            key={tbl.table_name}
            onClick={() => setActiveTable(tbl.table_name)}
            className={`px-3 py-1.5 rounded-md text-xs font-medium font-mono transition-all cursor-pointer ${
              effectiveActiveTable === tbl.table_name
                ? 'bg-primary text-white shadow-xs'
                : 'bg-white text-text-secondary hover:text-text-primary hover:bg-gray-50 border border-border'
            }`}
          >
            {tbl.table_name} ({tbl.columns.length})
          </button>
        ))}
      </div>

      {/* Main Grid: Policy Table + Policy Reference */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Columns & Policies Table (3 cols) */}
        <div className="lg:col-span-3 space-y-4">
          <Card className="p-0 overflow-hidden">
            <div className="px-5 py-3.5 bg-gray-50/70 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-text-primary uppercase tracking-wider">
                  Table: <span className="font-mono text-primary font-semibold">{effectiveActiveTable}</span>
                </span>
                <span className="text-xs text-text-muted">
                  ({currentTable?.columns?.length || 0} columns detected via SQLite PRAGMA)
                </span>
              </div>
              <span className="text-[11px] text-text-secondary flex items-center gap-1">
                <ShieldCheck className="w-3.5 h-3.5 text-success" />
                <span>Live Type Validator Active</span>
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-gray-100/60 text-text-secondary border-b border-border font-medium">
                    <th className="py-2.5 px-4">Column</th>
                    <th className="py-2.5 px-4">SQLite Raw Type</th>
                    <th className="py-2.5 px-4">Normalized Type</th>
                    <th className="py-2.5 px-4">Semantic Policy</th>
                    <th className="py-2.5 px-4">Validation Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {currentTable?.columns?.map((col) => {
                    const key = `${effectiveActiveTable}:${col.name}`;
                    const currentPolicy = policyAssignments[key] || 'LWW';
                    const validation = validationStates[key];
                    const isInvalid = validation && validation.valid === false;

                    return (
                      <tr
                        key={col.name}
                        className={`transition-colors ${
                          isInvalid ? 'bg-danger-light/50' : 'hover:bg-gray-50/70'
                        }`}
                      >
                        {/* Column Name */}
                        <td className="py-3 px-4 font-mono font-medium text-text-primary">
                          <div className="flex items-center gap-1.5">
                            {col.is_pk && (
                              <Key
                                className="w-3.5 h-3.5 text-amber-500 flex-shrink-0"
                                title="Primary Key"
                              />
                            )}
                            <span className={col.is_pk ? 'font-bold text-primary' : ''}>
                              {col.name}
                            </span>
                            {col.is_pk && (
                              <span className="text-[9px] bg-amber-100 text-amber-800 px-1 py-0.2 rounded-xs font-sans uppercase font-bold">
                                PK
                              </span>
                            )}
                          </div>
                        </td>

                        {/* Raw Type */}
                        <td className="py-3 px-4 font-mono text-text-secondary">
                          {col.raw_type || 'NONE'}
                        </td>

                        {/* Normalized Type */}
                        <td className="py-3 px-4">
                          <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded-sm bg-gray-100 text-text-primary">
                            {col.normalized_type}
                          </span>
                        </td>

                        {/* Policy Selector */}
                        <td className="py-3 px-4">
                          {col.is_pk ? (
                            <span className="text-text-muted italic text-[11px] font-mono">
                              [Primary Key - Immutable]
                            </span>
                          ) : (
                            <select
                              value={currentPolicy}
                              onChange={(e) => handlePolicyChange(activeTable, col, e.target.value)}
                              className={`text-xs font-mono font-semibold rounded-md px-2.5 py-1.5 border transition-all cursor-pointer ${
                                isInvalid
                                  ? 'border-danger text-danger bg-white focus:ring-danger/20'
                                  : 'border-border text-text-primary bg-white focus:border-primary focus:ring-primary/20'
                              }`}
                            >
                              {POLICIES.map((p) => (
                                <option key={p} value={p}>
                                  {p}
                                </option>
                              ))}
                            </select>
                          )}
                        </td>

                        {/* Validation Status */}
                        <td className="py-3 px-4">
                          {col.is_pk ? (
                            <span className="text-text-muted text-[11px]">—</span>
                          ) : isInvalid ? (
                            <div className="space-y-0.5">
                              <Badge variant="invalid" size="sm">
                                ❌ Incompatible
                              </Badge>
                              <p className="text-[10px] text-danger font-medium leading-tight max-w-xs mt-0.5">
                                {validation?.error_message || `${currentPolicy} cannot merge ${col.normalized_type}`}
                              </p>
                            </div>
                          ) : (
                            <Badge variant="valid" size="sm">
                              ✅ Valid
                            </Badge>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        {/* Right 1 Col: Policy Guide Card */}
        <div className="space-y-4">
          <Card className="p-4" title="Policy Semantics Matrix">
            <p className="text-xs text-text-secondary mb-3">
              SemanticSync guarantees deterministic resolution through type-aware policies:
            </p>

            <div className="space-y-2.5 text-xs">
              <div className="p-2.5 rounded-md bg-blue-50/70 border border-blue-200/50">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-primary">SUM</span>
                  <span className="text-[10px] text-text-muted font-mono">INTEGER, REAL</span>
                </div>
                <p className="text-[11px] text-text-secondary mt-1">
                  Computes additive delta: <code className="font-mono bg-white px-1 rounded">base + &Delta;A + &Delta;B</code>. Ideal for inventory counts & balances.
                </p>
              </div>

              <div className="p-2.5 rounded-md bg-emerald-50/70 border border-emerald-200/50">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-success">AVG</span>
                  <span className="text-[10px] text-text-muted font-mono">INTEGER, REAL</span>
                </div>
                <p className="text-[11px] text-text-secondary mt-1">
                  Arithmetic mean: <code className="font-mono bg-white px-1 rounded">(A + B) / 2.0</code>. Sensor readings, ratings, dosages.
                </p>
              </div>

              <div className="p-2.5 rounded-md bg-purple-50/70 border border-purple-200/50">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-[#8B5CF6]">APPEND</span>
                  <span className="text-[10px] text-text-muted font-mono">TEXT only</span>
                </div>
                <p className="text-[11px] text-text-secondary mt-1">
                  Deterministic concatenation. Preserves both authors' edits without silent loss.
                </p>
              </div>

              <div className="p-2.5 rounded-md bg-amber-50/70 border border-amber-200/50">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-warning">REJECT</span>
                  <span className="text-[10px] text-text-muted font-mono">Any datatype</span>
                </div>
                <p className="text-[11px] text-text-secondary mt-1">
                  Flags record for human review. Essential for blood types, clinical keys, or immutable SKUs.
                </p>
              </div>

              <div className="p-2.5 rounded-md bg-gray-50 border border-gray-200">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-text-primary">LWW</span>
                  <span className="text-[10px] text-text-muted font-mono">Any datatype</span>
                </div>
                <p className="text-[11px] text-text-secondary mt-1">
                  Last-Write-Wins via Hybrid Logical Clock (HLC). Default baseline behavior.
                </p>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
