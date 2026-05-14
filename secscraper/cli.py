"""Command-line interface for secscraper."""
from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from . import db as _db
from . import edgar, laws
from .http import PoliteClient


DEFAULT_DB = os.environ.get("SECSCRAPER_DB", "sec.db")


def cmd_init(args: argparse.Namespace) -> int:
    _db.init_db(args.database)
    print(f"Initialized database at {args.database}")
    return 0


def cmd_laws(args: argparse.Namespace) -> int:
    conn = _db.init_db(args.database)
    client = PoliteClient()
    n = laws.fetch_all(client, conn, ecfr=not args.no_ecfr)
    print(f"Done. {n} law documents touched.")
    return 0


def cmd_edgar(args: argparse.Namespace) -> int:
    conn = _db.init_db(args.database)
    client = PoliteClient()
    company_name: Optional[str] = None
    if args.ticker:
        cik, company_name = edgar.cik_for_ticker(client, args.ticker)
        print(f"{args.ticker.upper()} -> CIK {cik} ({company_name})")
    else:
        cik = edgar.normalize_cik(args.cik)
    types = (
        [t.strip() for t in args.types.split(",") if t.strip()]
        if args.types
        else None
    )
    n = edgar.fetch_filings(
        client,
        conn,
        cik=cik,
        ticker=args.ticker.upper() if args.ticker else None,
        company_name=company_name,
        types=types,
        limit=args.limit,
    )
    print(f"Done. {n} EDGAR filings touched.")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    conn = _db.connect(args.database)
    rows = _db.search(
        conn,
        args.query,
        source=args.source,
        doc_type=args.doc_type,
        limit=args.limit,
    )
    if not rows:
        print("No results.")
        return 0
    for r in rows:
        head = f"[{r['source']}/{r['doc_type'] or '-'}] {r['title']}"
        print(head)
        if r["identifier"]:
            print(f"  id:  {r['identifier']}")
        if r["filed_date"]:
            print(f"  filed: {r['filed_date']}")
        print(f"  url: {r['url']}")
        snippet = (r["snippet"] or "").replace("\n", " ")
        print(f"  ... {snippet} ...")
        print()
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    conn = _db.connect(args.database)
    rows = list(_db.counts_by_source(conn))
    if not rows:
        print("(empty database)")
        return 0
    print(f"{'source':8} {'doc_type':24} {'count':>8}")
    for row in rows:
        print(f"{row['source']:8} {(row['doc_type'] or '-'):24} {row['n']:>8}")
    total = sum(r["n"] for r in rows)
    print(f"{'TOTAL':8} {'':24} {total:>8}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="secscraper",
        description="Scrape SEC laws + EDGAR filings into a searchable "
                    "SQLite/FTS5 database.",
    )
    p.add_argument(
        "-d", "--database",
        default=DEFAULT_DB,
        help=f"SQLite database path (default: {DEFAULT_DB}; "
             "or set SECSCRAPER_DB).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s_init = sub.add_parser("init", help="Create the SQLite schema.")
    s_init.set_defaults(func=cmd_init)

    s_laws = sub.add_parser(
        "laws", help="Fetch SEC statutes and 17 CFR rules into the database."
    )
    s_laws.add_argument(
        "--no-ecfr", action="store_true",
        help="Skip the eCFR Title 17 download (only fetch statute PDFs).",
    )
    s_laws.set_defaults(func=cmd_laws)

    s_edgar = sub.add_parser(
        "edgar", help="Fetch EDGAR filings for a company."
    )
    grp = s_edgar.add_mutually_exclusive_group(required=True)
    grp.add_argument("--ticker", help="Company ticker (e.g. AAPL).")
    grp.add_argument("--cik", help="Central Index Key (e.g. 320193 or 0000320193).")
    s_edgar.add_argument(
        "--types",
        help="Comma-separated form types to keep, e.g. '10-K,10-Q,8-K'.",
    )
    s_edgar.add_argument(
        "--limit", type=int, default=10,
        help="Max filings to fetch (default 10).",
    )
    s_edgar.set_defaults(func=cmd_edgar)

    s_search = sub.add_parser("search", help="Full-text search the database.")
    s_search.add_argument("query", help="FTS5 query string.")
    s_search.add_argument(
        "--source", choices=["laws", "edgar"],
        help="Restrict to a source.",
    )
    s_search.add_argument(
        "--doc-type", help="Restrict to a specific doc_type (e.g. '10-K').",
    )
    s_search.add_argument("--limit", type=int, default=20)
    s_search.set_defaults(func=cmd_search)

    s_stats = sub.add_parser("stats", help="Show row counts by source/type.")
    s_stats.set_defaults(func=cmd_stats)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
