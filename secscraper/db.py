"""SQLite + FTS5 storage for scraped SEC documents."""
from __future__ import annotations

import datetime
import hashlib
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    doc_type TEXT,
    identifier TEXT,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    cik TEXT,
    ticker TEXT,
    filed_date TEXT,
    fetched_at TEXT NOT NULL,
    content_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source);
CREATE INDEX IF NOT EXISTS idx_documents_cik ON documents(cik);
CREATE INDEX IF NOT EXISTS idx_documents_ticker ON documents(ticker);
CREATE INDEX IF NOT EXISTS idx_documents_doc_type ON documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_documents_filed_date ON documents(filed_date);

CREATE TABLE IF NOT EXISTS document_text (
    document_id INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    body TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title,
    body,
    identifier,
    source UNINDEXED,
    doc_type UNINDEXED,
    tokenize='porter unicode61'
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path: str | Path) -> sqlite3.Connection:
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def upsert_document(
    conn: sqlite3.Connection,
    *,
    source: str,
    doc_type: Optional[str],
    identifier: Optional[str],
    title: str,
    url: str,
    body: str,
    cik: Optional[str] = None,
    ticker: Optional[str] = None,
    filed_date: Optional[str] = None,
) -> tuple[int, bool]:
    """Insert or update a document by URL. Returns (doc_id, changed)."""
    content_hash = hashlib.sha256(body.encode("utf-8", "replace")).hexdigest()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    row = conn.execute(
        "SELECT id, content_hash FROM documents WHERE url = ?", (url,)
    ).fetchone()

    if row and row["content_hash"] == content_hash:
        return row["id"], False

    if row:
        doc_id = row["id"]
        conn.execute(
            """UPDATE documents SET source=?, doc_type=?, identifier=?, title=?,
               cik=?, ticker=?, filed_date=?, fetched_at=?, content_hash=?
               WHERE id=?""",
            (source, doc_type, identifier, title, cik, ticker, filed_date,
             now, content_hash, doc_id),
        )
        conn.execute("DELETE FROM document_text WHERE document_id=?", (doc_id,))
        conn.execute("DELETE FROM documents_fts WHERE rowid=?", (doc_id,))
    else:
        cur = conn.execute(
            """INSERT INTO documents
               (source, doc_type, identifier, title, url, cik, ticker,
                filed_date, fetched_at, content_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (source, doc_type, identifier, title, url, cik, ticker,
             filed_date, now, content_hash),
        )
        doc_id = cur.lastrowid

    conn.execute(
        "INSERT INTO document_text (document_id, body) VALUES (?, ?)",
        (doc_id, body),
    )
    conn.execute(
        """INSERT INTO documents_fts
           (rowid, title, body, identifier, source, doc_type)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (doc_id, title or "", body, identifier or "", source, doc_type or ""),
    )
    conn.commit()
    return doc_id, True


def search(
    conn: sqlite3.Connection,
    query: str,
    *,
    source: Optional[str] = None,
    doc_type: Optional[str] = None,
    limit: int = 20,
) -> list[sqlite3.Row]:
    sql = [
        "SELECT d.id, d.source, d.doc_type, d.identifier, d.title, d.url,",
        "       d.cik, d.ticker, d.filed_date,",
        "       snippet(documents_fts, 1, '[', ']', ' … ', 12) AS snippet,",
        "       bm25(documents_fts) AS rank",
        "FROM documents_fts",
        "JOIN documents d ON d.id = documents_fts.rowid",
        "WHERE documents_fts MATCH ?",
    ]
    params: list = [query]
    if source:
        sql.append("AND d.source = ?")
        params.append(source)
    if doc_type:
        sql.append("AND d.doc_type = ?")
        params.append(doc_type)
    sql.append("ORDER BY rank LIMIT ?")
    params.append(limit)
    return conn.execute("\n".join(sql), params).fetchall()


def counts_by_source(conn: sqlite3.Connection) -> Iterable[sqlite3.Row]:
    return conn.execute(
        """SELECT source, doc_type, COUNT(*) AS n
           FROM documents
           GROUP BY source, doc_type
           ORDER BY source, n DESC"""
    ).fetchall()
