from datetime import date, timedelta
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from app.database import (
    get_papers_by_date, get_available_dates, get_paper_detail,
    get_arxiv_papers_by_date, get_arxiv_available_dates, get_arxiv_paper_detail,
    get_keyword_profiles, get_keyword_profile,
)
from app.keyword_matcher import filter_papers_by_keywords
from app.config import CONFIG_PATH

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def index(request: Request, date: str | None = None, profile_id: int | None = None):
    if not CONFIG_PATH.exists():
        return templates.TemplateResponse(request, "setup.html")

    today = date or _today()
    papers = await get_papers_by_date(today)
    profiles = await get_keyword_profiles()
    total_count = len(papers)

    if profile_id:
        profile = await get_keyword_profile(profile_id)
        if profile:
            papers = filter_papers_by_keywords(papers, profile["keywords"])

    prev_date = (_parse_date(today) - timedelta(days=1)).isoformat()
    next_date = (_parse_date(today) + timedelta(days=1)).isoformat()

    resp = templates.TemplateResponse(request, "index.html", context={
        "papers": papers,
        "current_date": today,
        "prev_date": prev_date,
        "next_date": next_date,
        "paper_count": len(papers),
        "total_count": total_count,
        "profiles": profiles,
        "current_profile_id": profile_id,
    })
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("/paper/{arxiv_id}")
async def paper_detail(request: Request, arxiv_id: str, date: str | None = None):
    paper = await get_paper_detail(arxiv_id, date)
    if not paper:
        return RedirectResponse("/")
    return templates.TemplateResponse(request, "paper_detail.html", context={"paper": paper})


# ── ArXiv pages ───────────────────────────────────────────────

@router.get("/arxiv")
async def arxiv_index(request: Request, date: str | None = None, profile_id: int | None = None):
    if not CONFIG_PATH.exists():
        return templates.TemplateResponse(request, "setup.html")

    today = date or _today()
    profiles = await get_keyword_profiles()

    # 获取当前 profile 的 categories
    current_profile = None
    categories_str = ""
    if profile_id:
        current_profile = await get_keyword_profile(profile_id)
        if current_profile:
            categories_str = current_profile.get("categories", "")

    papers = await get_arxiv_papers_by_date(today)
    total_count = len(papers)

    if current_profile:
        papers = filter_papers_by_keywords(papers, current_profile["keywords"])

    prev_date = (_parse_date(today) - timedelta(days=1)).isoformat()
    next_date = (_parse_date(today) + timedelta(days=1)).isoformat()

    resp = templates.TemplateResponse(request, "arxiv_index.html", context={
        "papers": papers,
        "current_date": today,
        "prev_date": prev_date,
        "next_date": next_date,
        "paper_count": len(papers),
        "total_count": total_count,
        "categories_str": categories_str,
        "profiles": profiles,
        "current_profile_id": profile_id,
    })
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("/arxiv/paper/{arxiv_id}")
async def arxiv_paper_detail(request: Request, arxiv_id: str, date: str | None = None):
    paper = await get_arxiv_paper_detail(arxiv_id, date)
    if not paper:
        return RedirectResponse("/arxiv")
    return templates.TemplateResponse(request, "arxiv_detail.html", context={"paper": paper})


# ── Profiles page ─────────────────────────────────────────────

@router.get("/setup")
async def setup_page(request: Request):
    profiles = await get_keyword_profiles()
    return templates.TemplateResponse(request, "setup.html", context={"profiles": profiles})


def _today() -> str:
    return date.today().isoformat()


def _parse_date(d: str):
    from datetime import date as dt_date
    try:
        parts = d.split("-")
        return dt_date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return dt_date.today()
