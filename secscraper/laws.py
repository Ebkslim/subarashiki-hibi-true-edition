"""Fetch SEC statutes and 17 CFR (regulations) into the database."""
from __future__ import annotations

from typing import Iterator, Optional
from urllib.parse import urljoin

from . import db as _db
from .http import PoliteClient
from .text import extract, html_to_text


LAWS_INDEX_URL = "https://www.sec.gov/about/laws.shtml"

# Known statute mirror URLs on sec.gov. The index page is also scraped at
# runtime, but this list anchors the most important documents.
KNOWN_STATUTES: list[tuple[str, str]] = [
    ("Securities Act of 1933", "https://www.sec.gov/about/laws/sa33.pdf"),
    ("Securities Exchange Act of 1934", "https://www.sec.gov/about/laws/sea34.pdf"),
    ("Trust Indenture Act of 1939", "https://www.sec.gov/about/laws/tia39.pdf"),
    ("Investment Company Act of 1940", "https://www.sec.gov/about/laws/ica40.pdf"),
    ("Investment Advisers Act of 1940", "https://www.sec.gov/about/laws/iaa40.pdf"),
    ("Sarbanes-Oxley Act of 2002", "https://www.sec.gov/about/laws/soa2002.pdf"),
    (
        "Dodd-Frank Wall Street Reform and Consumer Protection Act",
        "https://www.sec.gov/about/laws/wallstreetreform-cpa.pdf",
    ),
    (
        "Jumpstart Our Business Startups Act",
        "https://www.sec.gov/about/jumpstart-our-business-startups-act.pdf",
    ),
]


def _discover_statute_links(client: PoliteClient) -> list[tuple[str, str]]:
    from bs4 import BeautifulSoup

    try:
        r = client.get(LAWS_INDEX_URL)
    except Exception as exc:
        print(f"  warn: could not fetch laws index ({exc}); using known list only")
        return []
    soup = BeautifulSoup(r.text, "lxml")
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue
        url = urljoin(LAWS_INDEX_URL, href)
        if url in seen:
            continue
        text = a.get_text(strip=True)
        if not text or len(text) > 200:
            continue
        lower = url.lower()
        if lower.endswith(".pdf") or "/about/laws/" in lower:
            seen.add(url)
            found.append((text, url))
    return found


def fetch_statutes(client: PoliteClient, conn) -> int:
    targets: dict[str, str] = {}
    for title, url in KNOWN_STATUTES:
        targets[url] = title
    for title, url in _discover_statute_links(client):
        targets.setdefault(url, title)

    saved = 0
    for url, title in targets.items():
        try:
            r = client.get(url)
        except Exception as exc:
            print(f"  skip {url}: {exc}")
            continue
        body = extract(r.content, r.headers.get("Content-Type"), url)
        if not body.strip():
            print(f"  no extractable text: {url}")
            continue
        doc_type = "statute-pdf" if url.lower().endswith(".pdf") else "statute-html"
        _, changed = _db.upsert_document(
            conn,
            source="laws",
            doc_type=doc_type,
            identifier=title,
            title=title,
            url=url,
            body=body,
        )
        marker = "saved" if changed else "unchanged"
        print(f"  {marker}: {title}")
        saved += 1
    return saved


# ---------------------------------------------------------------------------
# 17 CFR via eCFR
# ---------------------------------------------------------------------------

ECFR_TITLES_URL = "https://www.ecfr.gov/api/versioner/v1/titles.json"
ECFR_FULL_TPL = "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-17.xml"


def _ecfr_latest_date(client: PoliteClient, title: str = "17") -> str:
    r = client.get(ECFR_TITLES_URL, accept="application/json")
    data = r.json()
    for t in data.get("titles", []):
        if str(t.get("number")) == str(title):
            return (
                t.get("latest_amended_on")
                or t.get("latest_issue_date")
                or t.get("up_to_date_as_of")
            )
    raise RuntimeError(f"Title {title} not found in eCFR titles list")


def _iter_cfr_parts(xml_bytes: bytes) -> Iterator[tuple[str, str, str]]:
    """Yield (part_number, title, body_text) for each PART in the title XML."""
    from lxml import etree

    root = etree.fromstring(xml_bytes)
    for elem in root.iter("DIV5"):
        if elem.get("TYPE") != "PART":
            continue
        part_num = elem.get("N", "").strip()
        head_el = elem.find("HEAD")
        head_text = (
            "".join(head_el.itertext()).strip() if head_el is not None else ""
        )
        title = head_text or f"17 CFR Part {part_num}"
        body = " ".join(
            t.strip() for t in elem.itertext() if t and t.strip()
        )
        yield part_num, title, body


def fetch_ecfr_title_17(client: PoliteClient, conn, *, date: Optional[str] = None) -> int:
    if date is None:
        date = _ecfr_latest_date(client, "17")
    full_url = ECFR_FULL_TPL.format(date=date)
    print(f"  eCFR Title 17 as of {date}")
    r = client.get(full_url, accept="application/xml")
    n = 0
    for part_num, title, body in _iter_cfr_parts(r.content):
        if not body.strip():
            continue
        url = f"https://www.ecfr.gov/current/title-17/part-{part_num}"
        identifier = f"17 CFR Part {part_num}"
        _, changed = _db.upsert_document(
            conn,
            source="laws",
            doc_type="cfr-part",
            identifier=identifier,
            title=f"{identifier} — {title}",
            url=url,
            body=body,
        )
        marker = "saved" if changed else "unchanged"
        print(f"  {marker}: {identifier}")
        n += 1
    return n


def fetch_all(client: PoliteClient, conn, *, ecfr: bool = True) -> int:
    total = 0
    print("Fetching SEC statute texts...")
    total += fetch_statutes(client, conn)
    if ecfr:
        print("Fetching 17 CFR from eCFR...")
        try:
            total += fetch_ecfr_title_17(client, conn)
        except Exception as exc:
            print(f"  eCFR fetch failed: {exc}")
    return total
