import re


def filter_papers_by_keywords(papers: list[dict], keywords_str: str) -> list[dict]:
    """Filter papers by comma-separated keywords. Whole-word match against title + abstract (case-insensitive)."""
    keywords = [k.strip().lower() for k in keywords_str.split(",") if k.strip()]
    if not keywords:
        return papers
    patterns = [re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE) for kw in keywords]
    return [p for p in papers if _matches(p, patterns)]


def _matches(paper: dict, patterns: list[re.Pattern]) -> bool:
    text = (paper.get("title", "") + " " + paper.get("abstract", ""))
    return any(pat.search(text) for pat in patterns)
