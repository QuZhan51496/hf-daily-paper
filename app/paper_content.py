import logging
import httpx
from bs4 import BeautifulSoup
import fitz  # pymupdf

logger = logging.getLogger(__name__)

ARXIV_HTML_URL = "https://arxiv.org/html/{arxiv_id}"
ARXIV_PDF_URL = "https://arxiv.org/pdf/{arxiv_id}"

MAX_CONTENT_CHARS = 80_000


async def fetch_paper_content(arxiv_id: str) -> tuple[str, str]:
    """获取论文全文，fallback: HTML -> PDF -> abstract_only"""
    text = await _fetch_html(arxiv_id)
    if text:
        return _truncate(text), "html"

    text = await _fetch_pdf(arxiv_id)
    if text:
        return _truncate(text), "pdf"

    return "", "abstract_only"


async def _fetch_html(arxiv_id: str) -> str | None:
    url = ARXIV_HTML_URL.format(arxiv_id=arxiv_id)
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.info(f"HTML not available for {arxiv_id} (status {resp.status_code})")
                return None
            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type:
                return None
            return _parse_html(resp.text)
    except Exception as e:
        logger.warning(f"HTML fetch failed for {arxiv_id}: {e}")
        return None


def _parse_html(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find("article")
    if not article:
        article = soup.find("div", class_="ltx_page_content")
    if not article:
        return None

    for tag in article.find_all(["figure", "table", "nav", "script", "style"]):
        tag.decompose()
    for bib in article.find_all("section", class_="ltx_bibliography"):
        bib.decompose()

    text = article.get_text(separator="\n", strip=True)
    lines = [line for line in text.split("\n") if line.strip()]
    return "\n".join(lines) if lines else None


async def _fetch_pdf(arxiv_id: str) -> str | None:
    url = ARXIV_PDF_URL.format(arxiv_id=arxiv_id)
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.info(f"PDF not available for {arxiv_id} (status {resp.status_code})")
                return None
            return _extract_pdf_text(resp.content)
    except Exception as e:
        logger.warning(f"PDF fetch failed for {arxiv_id}: {e}")
        return None


def _extract_pdf_text(pdf_bytes: bytes) -> str | None:
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        text = "\n".join(pages)
        return text if text.strip() else None
    except Exception as e:
        logger.warning(f"PDF text extraction failed: {e}")
        return None


def _truncate(text: str) -> str:
    if len(text) <= MAX_CONTENT_CHARS:
        return text
    truncated = text[:MAX_CONTENT_CHARS]
    last_newline = truncated.rfind("\n")
    if last_newline > MAX_CONTENT_CHARS * 0.8:
        truncated = truncated[:last_newline]
    return truncated + "\n\n[... content truncated ...]"
