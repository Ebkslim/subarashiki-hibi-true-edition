"""Fetch EDGAR filings via SEC's public JSON APIs."""
from __future__ import annotations

from typing import Iterable, Iterator, Optional

from . import db as _db
from .http import PoliteClient
from .text import extract


COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_TPL = "https://data.sec.gov/submissions/CIK{cik}.json"


def normalize_cik(cik: str | int) -> str:
    return str(cik).zfill(10)


def company_tickers(client: PoliteClient) -> dict:
    r = client.get(COMPANY_TICKERS_URL, accept="application/json")
    return r.json()


def cik_for_ticker(client: PoliteClient, ticker: str) -> tuple[str, str]:
    data = company_tickers(client)
    ticker_u = ticker.upper().strip()
    for entry in data.values():
        if str(entry.get("ticker", "")).upper() == ticker_u:
            return normalize_cik(entry["cik_str"]), entry.get("title", "")
    raise LookupError(f"Ticker not found in SEC tickers list: {ticker}")


def submissions(client: PoliteClient, cik: str) -> dict:
    r = client.get(SUBMISSIONS_TPL.format(cik=normalize_cik(cik)),
                   accept="application/json")
    return r.json()


def _iter_recent_filings(subs: dict) -> Iterator[dict]:
    recent = subs.get("filings", {}).get("recent", {})
    n = len(recent.get("accessionNumber", []))
    for i in range(n):
        yield {
            "accession": recent["accessionNumber"][i],
            "form": recent["form"][i],
            "filed": recent["filingDate"][i],
            "primary_doc": recent["primaryDocument"][i],
            "primary_doc_desc": recent.get("primaryDocDescription", [""] * n)[i],
            "report_date": recent.get("reportDate", [""] * n)[i],
        }


def select_filings(
    subs: dict,
    *,
    types: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
) -> list[dict]:
    wanted = {t.upper() for t in types} if types else None
    out: list[dict] = []
    for entry in _iter_recent_filings(subs):
        if wanted is not None and entry["form"].upper() not in wanted:
            continue
        out.append(entry)
        if limit is not None and len(out) >= limit:
            break
    return out


def filing_url(cik: str, accession: str, primary_doc: str) -> str:
    acc_nodash = accession.replace("-", "")
    cik_int = str(int(cik))
    return (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{cik_int}/{acc_nodash}/{primary_doc}"
    )


def fetch_filings(
    client: PoliteClient,
    conn,
    *,
    cik: str,
    ticker: Optional[str] = None,
    company_name: Optional[str] = None,
    types: Optional[Iterable[str]] = None,
    limit: int = 10,
) -> int:
    cik = normalize_cik(cik)
    subs = submissions(client, cik)
    if not company_name:
        company_name = subs.get("name", "")
    filings = select_filings(subs, types=types, limit=limit)
    if not filings:
        print(f"  no matching filings for CIK {cik}")
        return 0
    saved = 0
    for f in filings:
        url = filing_url(cik, f["accession"], f["primary_doc"])
        try:
            r = client.get(url)
        except Exception as exc:
            print(f"  skip {f['accession']} ({f['form']}): {exc}")
            continue
        body = extract(r.content, r.headers.get("Content-Type"), url)
        if not body.strip():
            print(f"  no extractable text: {url}")
            continue
        title = f"{company_name} — {f['form']} filed {f['filed']}"
        _, changed = _db.upsert_document(
            conn,
            source="edgar",
            doc_type=f["form"],
            identifier=f["accession"],
            title=title,
            url=url,
            body=body,
            cik=cik,
            ticker=ticker,
            filed_date=f["filed"],
        )
        marker = "saved" if changed else "unchanged"
        print(f"  {marker}: {title}")
        saved += 1
    return saved
