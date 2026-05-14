"""Text extraction helpers for HTML and PDF responses."""
from __future__ import annotations

import io
from typing import Optional


def html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    lines = (ln.strip() for ln in text.splitlines())
    return "\n".join(ln for ln in lines if ln)


def pdf_to_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception:
        return ""
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(p for p in parts if p).strip()


def extract(content: bytes, content_type: Optional[str], url: str) -> str:
    ct = (content_type or "").lower()
    lower_url = url.lower()
    if "pdf" in ct or lower_url.endswith(".pdf"):
        return pdf_to_text(content)
    if "xml" in ct and "html" not in ct:
        try:
            return content.decode("utf-8", "replace")
        except Exception:
            return ""
    try:
        return html_to_text(content.decode("utf-8", "replace"))
    except Exception:
        return ""
