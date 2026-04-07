import asyncio
import logging
import xml.etree.ElementTree as ET
import httpx
import re

logger = logging.getLogger(__name__)

ARXIV_API_URL = "http://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


async def fetch_arxiv_papers(date: str, category: str = "cs.AI", max_papers: int = 500) -> list[dict]:
    """Fetch arxiv papers for a specific date and category."""
    logger.info(f"Fetching arxiv papers for {category} on {date}")
    all_papers = []
    start = 0
    batch_size = 100

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        while start < max_papers:
            params = {
                "search_query": f"cat:{category}",
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "start": start,
                "max_results": batch_size,
            }
            try:
                resp = await client.get(ARXIV_API_URL, params=params)
                if resp.status_code != 200:
                    logger.warning(f"ArXiv API returned {resp.status_code}")
                    break
                entries = _parse_atom_feed(resp.text)
                if not entries:
                    break

                found_target = False
                found_older = False
                for entry in entries:
                    entry_date = entry["published_at"][:10] if entry.get("published_at") else ""
                    if entry_date == date:
                        all_papers.append(entry)
                        found_target = True
                    elif entry_date < date:
                        found_older = True
                        break

                if found_older or len(entries) < batch_size:
                    break

                start += batch_size
                if start < max_papers:
                    await asyncio.sleep(3)  # rate limit

            except Exception as e:
                logger.error(f"ArXiv fetch error: {e}")
                break

    logger.info(f"Fetched {len(all_papers)} arxiv papers for {category} on {date}")
    return all_papers


def _parse_atom_feed(xml_text: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    entries = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        arxiv_id = _extract_arxiv_id(entry.findtext(f"{ATOM_NS}id", ""))
        if not arxiv_id:
            continue

        title = entry.findtext(f"{ATOM_NS}title", "").strip()
        title = re.sub(r"\s+", " ", title)

        abstract = entry.findtext(f"{ATOM_NS}summary", "").strip()
        abstract = re.sub(r"\s+", " ", abstract)

        authors = []
        for author in entry.findall(f"{ATOM_NS}author"):
            name = author.findtext(f"{ATOM_NS}name", "").strip()
            if name:
                authors.append(name)

        primary_cat_el = entry.find(f"{ARXIV_NS}primary_category")
        primary_category = primary_cat_el.get("term", "") if primary_cat_el is not None else ""

        categories = []
        for cat in entry.findall(f"{ATOM_NS}category"):
            term = cat.get("term", "")
            if term:
                categories.append(term)

        published = entry.findtext(f"{ATOM_NS}published", "")
        updated = entry.findtext(f"{ATOM_NS}updated", "")

        entries.append({
            "arxiv_id": arxiv_id,
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "categories": categories,
            "primary_category": primary_category,
            "published_at": published,
            "updated_at": updated,
        })

    return entries


def _extract_arxiv_id(id_url: str) -> str:
    """Extract arxiv ID from URL like http://arxiv.org/abs/2501.12345v1"""
    match = re.search(r"arxiv\.org/abs/(.+?)(?:v\d+)?$", id_url)
    return match.group(1) if match else ""
