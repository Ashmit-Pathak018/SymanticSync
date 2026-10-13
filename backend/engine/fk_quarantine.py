"""Transactional foreign-key dependent-row quarantine helpers."""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any


def _q(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def enable_foreign_keys(conn: sqlite3.Connection) -> None:
    """Enable FK enforcement before a transaction starts; fail closed otherwise."""
    if conn.in_transaction:
        raise RuntimeError("PRAGMA foreign_keys must be enabled before a transaction")
    conn.execute("PRAGMA foreign_keys = ON")
    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise RuntimeError("SQLite foreign-key enforcement could not be enabled")


def connect_with_foreign_keys(path: str | Path, **kwargs: Any) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), **kwargs)
    try:
        enable_foreign_keys(conn)
    except Exception:
        conn.close()
        raise
    return conn


def ensure_quarantine_table(conn: sqlite3.Connection, schema: str = "main") -> None:
    conn.execute(f"""CREATE TABLE IF NOT EXISTS {_q(schema)}._ss_quarantine (
        quarantine_id TEXT PRIMARY KEY, table_name TEXT NOT NULL, row_id TEXT NOT NULL,
        row_payload TEXT NOT NULL, parent_table TEXT NOT NULL, parent_row_id TEXT NOT NULL,
        reason TEXT NOT NULL, quarantined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        resolved_at TEXT, status TEXT NOT NULL DEFAULT 'quarantined')""")


def verify_fk_integrity(conn: sqlite3.Connection, schema: str = "main") -> None:
    violations = conn.execute(f"PRAGMA {_q(schema)}.foreign_key_check").fetchall()
    if violations:
        raise sqlite3.IntegrityError(f"Foreign-key integrity violation: {violations[:5]}")


def _tables(conn: sqlite3.Connection, schema: str) -> list[str]:
    return [r[0] for r in conn.execute(
        f"SELECT name FROM {_q(schema)}.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )]


def _pk_cols(conn: sqlite3.Connection, table: str, schema: str) -> list[str]:
    rows = conn.execute(f"PRAGMA {_q(schema)}.table_info({_q(table)})").fetchall()
    return [r[1] for r in sorted(rows, key=lambda r: r[5]) if r[5] > 0]


def _foreign_keys(conn: sqlite3.Connection, child: str, schema: str) -> list[list[sqlite3.Row | tuple]]:
    rows = conn.execute(f"PRAGMA {_q(schema)}.foreign_key_list({_q(child)})").fetchall()
    groups: dict[int, list[Any]] = {}
    for row in rows:
        groups.setdefault(row[0], []).append(row)
    return [sorted(group, key=lambda r: r[1]) for group in groups.values()]


def _identity(row: dict[str, Any], pk: list[str], rowid: Any) -> tuple[str, list[tuple[str, Any]]]:
    if not pk:
        return str(rowid), [("rowid", rowid)]
    values = [(col, row[col]) for col in pk]
    return (str(values[0][1]) if len(values) == 1 else json.dumps(dict(values), sort_keys=True)), values


def quarantine_orphans(conn: sqlite3.Connection, parent_table: str, parent_row_id: Any,
                       schema: str = "main") -> list[str]:
    """Quarantine dependent rows recursively. Caller must hold a transaction."""
    if not conn.in_transaction:
        raise RuntimeError("quarantine_orphans requires an active transaction")
    ensure_quarantine_table(conn, schema)
    parent_pk = _pk_cols(conn, parent_table, schema)
    if not parent_pk:
        raise ValueError(f"Cannot quarantine dependencies for keyless table {parent_table}")
    if len(parent_pk) > 1 and not isinstance(parent_row_id, (dict, tuple, list)):
        raise ValueError(f"Composite primary key requires all key values: {parent_table}")
    if isinstance(parent_row_id, dict):
        pvals = parent_row_id
    elif len(parent_pk) == 1:
        pvals = {parent_pk[0]: parent_row_id}
    elif isinstance(parent_row_id, (tuple, list)) and len(parent_row_id) == len(parent_pk):
        pvals = dict(zip(parent_pk, parent_row_id))
    else:
        raise ValueError(f"Composite primary key requires {len(parent_pk)} values")
    parent = conn.execute(
        f"SELECT * FROM {_q(schema)}.{_q(parent_table)} WHERE " + " AND ".join(f"{_q(k)}=?" for k in pvals),
        tuple(pvals.values()),
    ).fetchone()
    if parent is None:
        return []
    parent_cols = [r[1] for r in conn.execute(f"PRAGMA {_q(schema)}.table_info({_q(parent_table)})")]
    return _quarantine_row(conn, parent_table, dict(zip(parent_cols, parent)), schema, set())


def _quarantine_row(conn: sqlite3.Connection, table: str, parent: dict[str, Any],
                    schema: str, visiting: set[tuple[str, str]]) -> list[str]:
    marker = (table, json.dumps(parent, sort_keys=True, default=str))
    if marker in visiting:
        raise ValueError(f"Cyclic foreign-key dependency at {table}")
    visiting = {*visiting, marker}
    made: list[str] = []
    for child_table in _tables(conn, schema):
        for group in _foreign_keys(conn, child_table, schema):
            if group[0][2] != table:
                continue
            pairs = [(r[3], r[4]) for r in group]
            if any(parent_col is None for _, parent_col in pairs):
                target_pk = _pk_cols(conn, table, schema)
                if len(target_pk) != len(pairs):
                    raise ValueError(f"Unsupported implicit composite FK {child_table} -> {table}")
                pairs = [(child_col, target_pk[i]) for i, (child_col, _) in enumerate(pairs)]
            if any(child_col is None or parent_col not in parent for child_col, parent_col in pairs):
                raise ValueError(f"Unsupported FK mapping {child_table} -> {table}")
            where = " AND ".join(f"{_q(c)}=?" for c, _ in pairs)
            vals = tuple(parent[p] for _, p in pairs)
            rows = conn.execute(f"SELECT rowid AS __ss_rowid, * FROM {_q(schema)}.{_q(child_table)} WHERE {where}", vals).fetchall()
            for raw in rows:
                desc = ["__ss_rowid"] + [r[1] for r in conn.execute(f"PRAGMA {_q(schema)}.table_info({_q(child_table)})")]
                child = dict(zip(desc, raw)); rowid = child.pop("__ss_rowid", None)
                pk = _pk_cols(conn, child_table, schema)
                if not pk and rowid is None:
                    raise ValueError(f"Cannot safely quarantine WITHOUT ROWID table {child_table}")
                # Recurse before removing this child so descendants are preserved first.
                made.extend(_quarantine_row(conn, child_table, child, schema, visiting))
                identity = [(c, child[c]) for c in pk] if pk else [("rowid", rowid)]
                row_id = str(identity[0][1]) if len(identity) == 1 else json.dumps(dict(identity), sort_keys=True)
                qid = str(uuid.uuid4())
                parent_pks = _pk_cols(conn, table, schema)
                parent_id = str(parent[parent_pks[0]]) if len(parent_pks) == 1 else json.dumps({k: parent[k] for k in parent_pks}, sort_keys=True)
                conn.execute(f"INSERT INTO {_q(schema)}._ss_quarantine(quarantine_id,table_name,row_id,row_payload,parent_table,parent_row_id,reason) VALUES(?,?,?,?,?,?,?)",
                             (qid, child_table, row_id, json.dumps(child, sort_keys=True, default=str), table, parent_id, f"dependent on {table}"))
                delwhere = " AND ".join(f"{_q(c)}=?" for c, _ in identity)
                conn.execute(f"DELETE FROM {_q(schema)}.{_q(child_table)} WHERE {delwhere}", tuple(v for _, v in identity))
                made.append(qid)
    return made

def list_quarantined(conn: sqlite3.Connection, status: str | None = "quarantined", schema: str = "main", table_name: str | None = None) -> list[dict[str, Any]]:
    clauses: list[str] = []; args: list[Any] = []
    if status is not None: clauses.append("status=?"); args.append(status)
    if table_name is not None: clauses.append("table_name=?"); args.append(table_name)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    cursor = conn.execute(f"SELECT * FROM {_q(schema)}._ss_quarantine{where} ORDER BY quarantined_at, quarantine_id", args)
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def resolve_quarantine_record(conn: sqlite3.Connection, quarantine_id: str, action: str,
                              new_parent_row_id: Any = None, schema: str = "main") -> bool:
    """Confirm deletion or restore a quarantined row against an existing parent atomically."""
    own_tx = not conn.in_transaction
    if own_tx:
        conn.execute("BEGIN IMMEDIATE")
    try:
        result = _resolve_quarantine_record_in_tx(conn, quarantine_id, action, new_parent_row_id, schema)
        if own_tx:
            conn.commit()
        return result
    except Exception:
        if own_tx:
            conn.rollback()
        raise


def _resolve_quarantine_record_in_tx(conn: sqlite3.Connection, quarantine_id: str, action: str,
                                     new_parent_row_id: Any, schema: str) -> bool:
    if action not in {"confirmed_deleted", "relinked"}:
        raise ValueError("action must be confirmed_deleted or relinked")
    cursor = conn.execute(f"SELECT * FROM {_q(schema)}._ss_quarantine WHERE quarantine_id=? AND status='quarantined'", (quarantine_id,))
    raw_record = cursor.fetchone()
    record = dict(zip([d[0] for d in cursor.description], raw_record)) if raw_record else None
    if record is None:
        return False
    if action == "relinked":
        if new_parent_row_id is None:
            raise ValueError("new_parent_row_id is required for relink")
        row = json.loads(record["row_payload"])
        groups = [g for g in _foreign_keys(conn, record["table_name"], schema) if g[0][2] == record["parent_table"]]
        if len(groups) != 1 or len(groups[0]) != 1:
            raise ValueError("Relinking requires exactly one single-column FK to the recorded parent")
        fk = groups[0][0]; parent_table = fk[2]; child_col = fk[3]; parent_col = fk[4]
        pks = _pk_cols(conn, parent_table, schema)
        if parent_col is None: parent_col = pks[0] if len(pks) == 1 else None
        if parent_col is None or len(pks) != 1:
            raise ValueError("Relinking composite parent keys is unsupported")
        parent = conn.execute(f"SELECT {_q(parent_col)} FROM {_q(schema)}.{_q(parent_table)} WHERE {_q(pks[0])}=?", (new_parent_row_id,)).fetchone()
        if parent is None: raise ValueError("Relink parent does not exist")
        row[child_col] = parent[0]
        cols = list(row)
        child_pks = _pk_cols(conn, record["table_name"], schema)
        if not child_pks:
            raise ValueError("Relinking keyless child tables is unsupported")
        inserted = conn.execute(f"INSERT INTO {_q(schema)}.{_q(record['table_name'])}({','.join(_q(c) for c in cols)}) VALUES({','.join('?' for _ in cols)})", tuple(row[c] for c in cols))
        if inserted.rowcount != 1:
            raise sqlite3.IntegrityError("Relink insert did not affect exactly one child row")
        key_where = " AND ".join(f"{_q(col)}=?" for col in child_pks)
        check = conn.execute(f"SELECT * FROM {_q(schema)}.{_q(record['table_name'])} WHERE {key_where}", tuple(row[col] for col in child_pks))
        persisted = check.fetchone()
        stored = dict(zip([d[0] for d in check.description], persisted)) if persisted else None
        if stored != row:
            raise sqlite3.IntegrityError("Relinked child row differs from the quarantined payload")
        verify_fk_integrity(conn, schema)
    cur = conn.execute(f"UPDATE {_q(schema)}._ss_quarantine SET status=?, resolved_at=CURRENT_TIMESTAMP WHERE quarantine_id=? AND status='quarantined'", (action, quarantine_id))
    return cur.rowcount == 1
