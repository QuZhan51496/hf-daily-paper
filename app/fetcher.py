import httpx
import logging

logger = logging.getLogger(__name__)

HF_API_URL = "https://huggingface.co/api/daily_papers"


async def fetch_daily_papers(date: str) -> list[dict]:
    url = f"{HF_API_URL}?date={date}"
    logger.info(f"Fetching papers from {url}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        if resp.status_code == 400:
            logger.info(f"No papers available for {date} (400)")
            return []
        resp.raise_for_status()
        items = resp.json()

    papers = []
    for item in items:
        paper = item.get("paper", {})
        authors = [a.get("name", "") for a in paper.get("authors", []) if a.get("name")]
        papers.append({
            "arxiv_id": paper.get("id", ""),
            "title": paper.get("title", ""),
            "abstract": paper.get("summary", ""),
            "hf_ai_summary": paper.get("ai_summary"),
            "authors": authors,
            "keywords": paper.get("ai_keywords", []),
            "upvotes": paper.get("upvotes", 0),
            "num_comments": item.get("numComments", 0),
            "thumbnail_url": item.get("thumbnail"),
            "github_repo": paper.get("githubRepo"),
            "github_stars": paper.get("githubStars"),
            "project_page": paper.get("projectPage"),
            "published_at": paper.get("publishedAt"),
            "submitted_daily_at": paper.get("submittedOnDailyAt"),
        })

    logger.info(f"Fetched {len(papers)} papers for {date}")
    return papers
