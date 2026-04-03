from datetime import date, timedelta
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from app.database import get_papers_by_date, get_available_dates, get_paper_detail
from app.config import CONFIG_PATH

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def index(request: Request, date: str | None = None):
    if not CONFIG_PATH.exists():
        return templates.TemplateResponse(request, "setup.html")

    today = date or _today()
    papers = await get_papers_by_date(today)
    dates = await get_available_dates()

    prev_date = (_parse_date(today) - timedelta(days=1)).isoformat()
    next_date = (_parse_date(today) + timedelta(days=1)).isoformat()

    resp = templates.TemplateResponse(request, "index.html", context={
        "papers": papers,
        "current_date": today,
        "dates": dates,
        "prev_date": prev_date,
        "next_date": next_date,
        "paper_count": len(papers),
    })
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("/paper/{arxiv_id}")
async def paper_detail(request: Request, arxiv_id: str, date: str | None = None):
    paper = await get_paper_detail(arxiv_id, date)
    if not paper:
        return templates.TemplateResponse(request, "index.html", context={
            "papers": [], "current_date": _today(),
            "dates": [], "prev_date": "", "next_date": "", "paper_count": 0,
        })
    return templates.TemplateResponse(request, "paper_detail.html", context={
        "paper": paper,
    })


@router.get("/setup")
async def setup_page(request: Request):
    return templates.TemplateResponse(request, "setup.html")


def _today() -> str:
    return date.today().isoformat()


def _parse_date(d: str):
    from datetime import date as dt_date
    try:
        parts = d.split("-")
        return dt_date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return dt_date.today()
