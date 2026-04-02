import asyncio
import logging
from datetime import date
from fastapi import APIRouter, HTTPException
from app.database import (
    get_papers_by_date, get_available_dates, get_paper_detail,
    is_date_fetched, insert_papers, update_llm_summary,
)
from app.fetcher import fetch_daily_papers
from app.summarizer import generate_brief, generate_detail, generate_briefs_batch
from app.database import update_brief_summary
from app.models import PaperResponse, SetupRequest
from app.config import Settings, save_config, load_config, CONFIG_PATH

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/papers")
async def api_papers(date: str | None = None):
    if not date:
        date = _today()
    papers = await get_papers_by_date(date)
    return [PaperResponse.from_db(p) for p in papers]


@router.get("/papers/{arxiv_id}")
async def api_paper_detail(arxiv_id: str, date: str | None = None):
    paper = await get_paper_detail(arxiv_id, date)
    if not paper:
        raise HTTPException(404, "Paper not found")
    return PaperResponse.from_db(paper)


@router.get("/dates")
async def api_dates():
    return await get_available_dates()


@router.post("/fetch")
async def api_fetch(date: str | None = None):
    if not date:
        date = _today()
    try:
        papers = await fetch_daily_papers(date)
        count = 0
        if papers:
            count = await insert_papers(date, papers)
            all_papers = await get_papers_by_date(date)
            need_brief = [p for p in all_papers if p.get("brief_summary_status") != "completed"]
            if need_brief:
                asyncio.ensure_future(generate_briefs_batch(need_brief))
        return {"date": date, "fetched": len(papers), "inserted": count, "status": "ok"}
    except Exception as e:
        logger.error(f"Fetch failed for {date}: {e}")
        raise HTTPException(500, str(e))


@router.post("/regenerate_brief/{paper_id}")
async def api_regenerate_brief(paper_id: int):
    """重新生成首页极简概要"""
    import aiosqlite
    from app.database import DB_PATH

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, "Paper not found")
        paper = dict(row)

    try:
        summary = await generate_brief(paper["title"], paper.get("abstract", ""))
        await update_brief_summary(paper_id, summary, "completed")
        return {"status": "ok", "summary": summary}
    except Exception as e:
        await update_brief_summary(paper_id, str(e), "failed")
        raise HTTPException(500, str(e))


@router.post("/resummarize/{paper_id}")
async def api_resummarize(paper_id: int):
    """重新生成完整分析"""
    import aiosqlite
    from app.database import DB_PATH

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, "Paper not found")
        paper = dict(row)

    try:
        summary = await generate_detail(
            paper["title"], paper.get("abstract", ""), arxiv_id=paper.get("arxiv_id")
        )
        await update_llm_summary(paper_id, summary, "completed")
        return {"status": "ok", "summary": summary}
    except Exception as e:
        await update_llm_summary(paper_id, str(e), "failed")
        raise HTTPException(500, str(e))


@router.post("/generate_detail/{paper_id}")
async def api_generate_detail(paper_id: int):
    """详情页触发：生成完整分析"""
    import aiosqlite
    from app.database import DB_PATH

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, "Paper not found")
        paper = dict(row)

    # 已有完整分析则直接返回
    if paper.get("llm_summary_status") == "completed" and paper.get("llm_summary"):
        return {"status": "ok", "summary": paper["llm_summary"]}

    try:
        summary = await generate_detail(
            paper["title"], paper.get("abstract", ""), arxiv_id=paper.get("arxiv_id")
        )
        await update_llm_summary(paper_id, summary, "completed")
        return {"status": "ok", "summary": summary}
    except Exception as e:
        await update_llm_summary(paper_id, str(e), "failed")
        raise HTTPException(500, str(e))


@router.get("/config")
async def api_get_config():
    if not CONFIG_PATH.exists():
        return {"has_key": False, "llm_base_url": "https://api.openai.com/v1", "llm_model": "gpt-4o-mini"}
    try:
        config = load_config()
        return {
            "has_key": bool(config.llm_api_key),
            "llm_base_url": config.llm_base_url,
            "llm_model": config.llm_model,
        }
    except Exception:
        return {"has_key": False, "llm_base_url": "https://api.openai.com/v1", "llm_model": "gpt-4o-mini"}


@router.post("/setup")
async def api_setup(req: SetupRequest):
    # 如果未提供 api_key，保留现有的
    api_key = req.llm_api_key
    if not api_key and CONFIG_PATH.exists():
        try:
            existing = load_config()
            api_key = existing.llm_api_key
        except Exception:
            pass
    if not api_key:
        raise HTTPException(400, "API Key 不能为空")
    settings = Settings(
        llm_api_key=api_key,
        llm_base_url=req.llm_base_url,
        llm_model=req.llm_model,
    )
    save_config(settings)
    return {"status": "ok", "message": "配置已保存"}


@router.get("/status")
async def api_status():
    config_exists = CONFIG_PATH.exists()
    today = _today()
    fetched = await is_date_fetched(today) if config_exists else False
    return {
        "configured": config_exists,
        "today": today,
        "today_fetched": fetched,
    }


def _today() -> str:
    return date.today().isoformat()
