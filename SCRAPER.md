# secscraper

A small Python tool that pulls U.S. SEC content into a local SQLite database
with FTS5 full-text search, so you can grep / query securities law and EDGAR
filings without hitting sec.gov repeatedly.

Two sources are supported:

| Source | What it grabs                                           | Origin              |
|--------|----------------------------------------------------------|---------------------|
| `laws` | Federal securities statutes (1933 Act, 1934 Act, etc.)   | `sec.gov/about/laws`|
| `laws` | 17 CFR (Commodity & Securities Exchanges regulations)    | `ecfr.gov` API      |
| `edgar`| Company filings (10-K, 10-Q, 8-K, S-1, …) by CIK/ticker  | `data.sec.gov` API  |

Everything is stored in a single `documents` table with a parallel FTS5 index;
`secscraper search` returns ranked snippets via BM25.

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Required: set a contact User-Agent

The SEC requires every request to identify a real human contact. The scraper
refuses to start without one:

```bash
export SEC_USER_AGENT="Jane Researcher jane@example.com"
```

## Quick start

```bash
# 1. create the database
secscraper init                       # → ./sec.db  (override with -d / SECSCRAPER_DB)

# 2. mirror the law book (statutes + 17 CFR)
secscraper laws

# 3. mirror a company's recent filings
secscraper edgar --ticker AAPL --types 10-K,10-Q --limit 8
secscraper edgar --cik 0000320193 --types 8-K --limit 25

# 4. search
secscraper search 'insider trading'
secscraper search '"material non-public"' --source laws
secscraper search 'revenue recognition' --source edgar --doc-type 10-K

# 5. show what you've got
secscraper stats
```

Search queries use SQLite's [FTS5 query syntax]:

| Query                          | Meaning                              |
|--------------------------------|---------------------------------------|
| `safe harbor`                  | both terms (AND)                      |
| `"safe harbor"`                | exact phrase                          |
| `disgorge*`                    | prefix match                          |
| `tender NEAR/5 offer`          | within 5 tokens                       |
| `title:"securities act"`       | restrict to title column              |

[FTS5 query syntax]: https://sqlite.org/fts5.html#full_text_query_syntax

## Storage

A single SQLite file (default `sec.db`). Schema:

- `documents` — one row per fetched URL with metadata
  (`source`, `doc_type`, `identifier`, `title`, `url`, `cik`, `ticker`,
   `filed_date`, `fetched_at`, `content_hash`).
- `document_text` — the extracted plain text body.
- `documents_fts` — FTS5 virtual table over `title`, `body`, `identifier`.

Re-running a fetch is idempotent: documents are matched by URL, content is
hashed, and unchanged documents are skipped.

## Project layout

```
secscraper/
├── __init__.py
├── cli.py        # argparse entrypoint (`secscraper …`)
├── db.py         # SQLite + FTS5 schema, upsert, search
├── edgar.py      # EDGAR submissions API + filing fetch
├── http.py       # rate-limited HTTP client (10 req/s, UA validation, retries)
├── laws.py       # SEC statutes + eCFR Title 17
└── text.py       # HTML/PDF → text extraction
```

## Compliance notes

- The client enforces ~8 req/s to stay well under the SEC's 10 req/s cap.
- 429 / 5xx responses trigger exponential backoff with `Retry-After` honored.
- The User-Agent must contain a real email; the client refuses to start
  otherwise. This is the SEC's published requirement.
- This project does not redistribute SEC content; it just helps you fetch and
  index it locally for your own use.
