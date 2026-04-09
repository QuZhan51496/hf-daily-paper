import asyncio
import logging
from datetime import date
from fastapi import APIRouter, HTTPException
from app.database import (
    get_papers_by_date, get_available_dates, get_paper_detail,
    is_date_fetched, insert_papers, update_llm_summary,
    update_brief_summary, get_paper_by_id,
    insert_arxiv_papers, get_arxiv_papers_by_date, get_arxiv_paper_by_id,
    get_arxiv_available_dates, update_arxiv_llm_summary, update_arxiv_brief_summary,
    get_keyword_profiles, get_keyword_profile, create_keyword_profile,
    update_keyword_profile, delete_keyword_profile,
    get_hf_papers_need_detail, get_arxiv_papers_need_detail,
)
from app.fetcher import fetch_daily_papers
from app.arxiv_fetcher import fetch_arxiv_papers
from app.summarizer import generate_brief, generate_detail, generate_briefs_batch, generate_arxiv_briefs_batch
from app.keyword_matcher import filter_papers_by_keywords
from app.models import PaperResponse, ArxivPaperResponse, KeywordProfileCreate, SetupRequest
from app.config import Settings, save_config, load_config, CONFIG_PATH

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


async def _auto_analyze_details(date: str, source: str = "hf"):
    """对开启 auto_analyze 的 profile 匹配到的论文触发详细分析"""
    profiles = await get_keyword_profiles()
    analyze_profiles = [p for p in profiles if int(p.get("auto_analyze") or 0)]
    if not analyze_profiles:
        return

    if source == "hf":
        need = await get_hf_papers_need_detail(date)
    else:
        need = await get_arxiv_papers_need_detail(date)
    if not need:
        return

    analyze_ids = set()
    for prof in analyze_profiles:
        kw = prof.get("keywords", "")
        for p in filter_papers_by_keywords(need, kw):
            analyze_ids.add(p["id"])

    for paper in need:
        if paper["id"] not in analyze_ids:
            continue
        try:
            summary = await generate_detail(
                paper["title"], paper.get("abstract", ""), arxiv_id=paper.get("arxiv_id")
            )
            if source == "hf":
                await update_llm_summary(paper["id"], summary, "completed")
            else:
                await update_arxiv_llm_summary(paper["id"], summary, "completed")
            logger.info(f"Auto-analyze {source} detail done: {paper['title'][:50]}...")
        except Exception as e:
            logger.error(f"Auto-analyze {source} detail failed {paper['id']}: {e}")
            if source == "hf":
                await update_llm_summary(paper["id"], str(e), "failed")
            else:
                await update_arxiv_llm_summary(paper["id"], str(e), "failed")


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
            if count > 0:
                all_papers = await get_papers_by_date(date)
                need_brief = [p for p in all_papers if p.get("brief_summary_status") != "completed"]
                if need_brief:
                    asyncio.ensure_future(generate_briefs_batch(need_brief))
                asyncio.ensure_future(_auto_analyze_details(date, "hf"))
        return {"date": date, "fetched": len(papers), "inserted": count, "status": "ok"}
    except Exception as e:
        logger.error(f"Fetch failed for {date}: {e}")
        raise HTTPException(500, str(e))


@router.post("/regen_briefs")
async def api_regen_briefs(date: str | None = None, profile_id: int | None = None):
    """批量重新生成 HF 论文缺失的概要"""
    if not date:
        date = _today()
    papers = await get_papers_by_date(date)
    if profile_id:
        profile = await get_keyword_profile(profile_id)
        if profile and profile.get("keywords"):
            papers = filter_papers_by_keywords(papers, profile["keywords"])
    need = [p for p in papers if p.get("brief_summary_status") != "completed"]
    if need:
        asyncio.ensure_future(generate_briefs_batch(need))
    return {"status": "ok", "count": len(need)}


@router.post("/regenerate_brief/{paper_id}")
async def api_regenerate_brief(paper_id: int):
    """重新生成首页极简概要"""
    paper = await get_paper_by_id(paper_id)
    if not paper:
        raise HTTPException(404, "Paper not found")

    try:
        summary = await generate_brief(paper["title"], paper.get("abstract", ""), arxiv_id=paper.get("arxiv_id"))
        await update_brief_summary(paper_id, summary, "completed")
        return {"status": "ok", "summary": summary}
    except Exception as e:
        await update_brief_summary(paper_id, str(e), "failed")
        raise HTTPException(500, str(e))


@router.post("/resummarize/{paper_id}")
async def api_resummarize(paper_id: int):
    """重新生成完整分析"""
    paper = await get_paper_by_id(paper_id)
    if not paper:
        raise HTTPException(404, "Paper not found")

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
    paper = await get_paper_by_id(paper_id)
    if not paper:
        raise HTTPException(404, "Paper not found")

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
            "auto_fetch_interval": config.auto_fetch_interval,
        }
    except Exception:
        return {"has_key": False, "llm_base_url": "https://api.openai.com/v1", "llm_model": "gpt-4o-mini", "auto_fetch_interval": 0}


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
        auto_fetch_interval=req.auto_fetch_interval,
    )
    save_config(settings)
    # 重启定时任务
    from app.auto_fetch import start_auto_fetch, stop_auto_fetch
    if settings.auto_fetch_interval > 0:
        start_auto_fetch()
    else:
        stop_auto_fetch()
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


# ── ArXiv paper endpoints ─────────────────────────────────────

@router.get("/arxiv/papers")
async def api_arxiv_papers(date: str | None = None, profile_id: int | None = None):
    if not date:
        date = _today()
    papers = await get_arxiv_papers_by_date(date)
    if profile_id:
        profile = await get_keyword_profile(profile_id)
        if profile:
            papers = filter_papers_by_keywords(papers, profile["keywords"])
    return [ArxivPaperResponse.from_db(p) for p in papers]


@router.get("/arxiv/dates")
async def api_arxiv_dates(category: str | None = None):
    return await get_arxiv_available_dates(category)


@router.post("/arxiv/fetch")
async def api_arxiv_fetch(date: str | None = None, categories: str = "cs.AI"):
    """Fetch arxiv papers for one or more categories (comma-separated)."""
    if not date:
        date = _today()
    cat_list = [c.strip() for c in categories.split(",") if c.strip()]
    if not cat_list:
        cat_list = ["cs.AI"]
    total_fetched = 0
    total_inserted = 0
    try:
        for cat in cat_list:
            papers = await fetch_arxiv_papers(date, cat)
            total_fetched += len(papers)
            if papers:
                inserted = await insert_arxiv_papers(date, cat, papers)
                total_inserted += inserted
        if total_inserted > 0:
            all_papers = await get_arxiv_papers_by_date(date)
            need_brief = [p for p in all_papers if p.get("brief_summary_status") != "completed"]
            if need_brief:
                asyncio.ensure_future(generate_arxiv_briefs_batch(need_brief))
            asyncio.ensure_future(_auto_analyze_details(date, "arxiv"))
        return {"date": date, "categories": categories, "fetched": total_fetched, "inserted": total_inserted, "status": "ok"}
    except Exception as e:
        logger.error(f"ArXiv fetch failed for {categories} {date}: {e}")
        raise HTTPException(500, str(e))


@router.post("/arxiv/regen_briefs")
async def api_arxiv_regen_briefs(date: str | None = None, profile_id: int | None = None):
    """批量重新生成 ArXiv 论文缺失的概要"""
    if not date:
        date = _today()
    papers = await get_arxiv_papers_by_date(date)
    if profile_id:
        profile = await get_keyword_profile(profile_id)
        if profile and profile.get("keywords"):
            papers = filter_papers_by_keywords(papers, profile["keywords"])
    need = [p for p in papers if p.get("brief_summary_status") != "completed"]
    if need:
        asyncio.ensure_future(generate_arxiv_briefs_batch(need))
    return {"status": "ok", "count": len(need)}


@router.post("/arxiv/regenerate_brief/{paper_id}")
async def api_arxiv_regenerate_brief(paper_id: int):
    paper = await get_arxiv_paper_by_id(paper_id)
    if not paper:
        raise HTTPException(404, "Paper not found")
    try:
        summary = await generate_brief(paper["title"], paper.get("abstract", ""), arxiv_id=paper.get("arxiv_id"))
        await update_arxiv_brief_summary(paper_id, summary, "completed")
        return {"status": "ok", "summary": summary}
    except Exception as e:
        await update_arxiv_brief_summary(paper_id, str(e), "failed")
        raise HTTPException(500, str(e))


@router.post("/arxiv/generate_detail/{paper_id}")
async def api_arxiv_generate_detail(paper_id: int):
    paper = await get_arxiv_paper_by_id(paper_id)
    if not paper:
        raise HTTPException(404, "Paper not found")
    if paper.get("llm_summary_status") == "completed" and paper.get("llm_summary"):
        return {"status": "ok", "summary": paper["llm_summary"]}
    try:
        summary = await generate_detail(paper["title"], paper.get("abstract", ""), arxiv_id=paper.get("arxiv_id"))
        await update_arxiv_llm_summary(paper_id, summary, "completed")
        return {"status": "ok", "summary": summary}
    except Exception as e:
        await update_arxiv_llm_summary(paper_id, str(e), "failed")
        raise HTTPException(500, str(e))


@router.post("/arxiv/resummarize/{paper_id}")
async def api_arxiv_resummarize(paper_id: int):
    paper = await get_arxiv_paper_by_id(paper_id)
    if not paper:
        raise HTTPException(404, "Paper not found")
    try:
        summary = await generate_detail(paper["title"], paper.get("abstract", ""), arxiv_id=paper.get("arxiv_id"))
        await update_arxiv_llm_summary(paper_id, summary, "completed")
        return {"status": "ok", "summary": summary}
    except Exception as e:
        await update_arxiv_llm_summary(paper_id, str(e), "failed")
        raise HTTPException(500, str(e))


# ── Keyword profile endpoints ────────────────────────────────

@router.get("/profiles")
async def api_list_profiles():
    return await get_keyword_profiles()


@router.post("/profiles")
async def api_create_profile(req: KeywordProfileCreate):
    try:
        pid = await create_keyword_profile(req.name, req.keywords, req.categories, req.auto_analyze)
        return {"status": "ok", "id": pid}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.put("/profiles/{profile_id}")
async def api_update_profile(profile_id: int, req: KeywordProfileCreate):
    profile = await get_keyword_profile(profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")
    await update_keyword_profile(profile_id, req.name, req.keywords, req.categories, req.auto_analyze)
    return {"status": "ok"}


@router.delete("/profiles/{profile_id}")
async def api_delete_profile(profile_id: int):
    await delete_keyword_profile(profile_id)
    return {"status": "ok"}


def _today() -> str:
    return date.today().isoformat()
