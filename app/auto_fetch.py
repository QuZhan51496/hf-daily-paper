import asyncio
import logging
from datetime import date

from app.config import load_config, CONFIG_PATH
from app.database import (
    get_keyword_profiles, get_papers_by_date, get_arxiv_papers_by_date,
    insert_papers, insert_arxiv_papers,
    get_hf_papers_need_detail, get_arxiv_papers_need_detail,
    update_llm_summary, update_arxiv_llm_summary,
)
from app.keyword_matcher import filter_papers_by_keywords
from app.fetcher import fetch_daily_papers
from app.arxiv_fetcher import fetch_arxiv_papers
from app.summarizer import (
    generate_briefs_batch, generate_arxiv_briefs_batch, generate_detail,
)

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


def start_auto_fetch():
    global _task
    stop_auto_fetch()
    _task = asyncio.ensure_future(_auto_fetch_loop())
    logger.info("Auto-fetch task started")


def stop_auto_fetch():
    global _task
    if _task and not _task.done():
        _task.cancel()
        logger.info("Auto-fetch task stopped")
    _task = None


async def _auto_fetch_loop():
    while True:
        try:
            if not CONFIG_PATH.exists():
                await asyncio.sleep(60)
                continue

            config = load_config()
            interval = config.auto_fetch_interval
            if interval <= 0:
                await asyncio.sleep(60)
                continue

            today = date.today().isoformat()
            logger.info(f"Auto-fetch: starting for {today}")

            # 1. 抓取 HF 论文
            try:
                hf_papers = await fetch_daily_papers(today)
                if hf_papers:
                    inserted = await insert_papers(today, hf_papers)
                    logger.info(f"Auto-fetch: HF inserted {inserted} papers")
                    if inserted > 0:
                        all_hf = await get_papers_by_date(today)
                        need_brief = [p for p in all_hf if p.get("brief_summary_status") != "completed"]
                        if need_brief:
                            await generate_briefs_batch(need_brief)
            except Exception as e:
                logger.error(f"Auto-fetch HF error: {e}")

            # 2. 抓取 ArXiv 论文（遍历所有 profile 的 categories）
            profiles = await get_keyword_profiles()
            fetched_cats = set()
            for profile in profiles:
                cats = profile.get("categories", "")
                for cat in [c.strip() for c in cats.split(",") if c.strip()]:
                    if cat not in fetched_cats:
                        fetched_cats.add(cat)
                        try:
                            papers = await fetch_arxiv_papers(today, cat)
                            if papers:
                                inserted = await insert_arxiv_papers(today, cat, papers)
                                logger.info(f"Auto-fetch: ArXiv {cat} inserted {inserted} papers")
                        except Exception as e:
                            logger.error(f"Auto-fetch ArXiv {cat} error: {e}")

            # 为所有未生成 brief 的 arxiv 论文生成概要
            all_arxiv = await get_arxiv_papers_by_date(today)
            need_arxiv_brief = [p for p in all_arxiv if p.get("brief_summary_status") != "completed"]
            if need_arxiv_brief:
                await generate_arxiv_briefs_batch(need_arxiv_brief)

            # 3. 预生成详细分析（仅 auto_analyze 开启的 profile 匹配到的论文）
            analyze_profiles = [p for p in profiles if int(p.get("auto_analyze") or 0)]
            if analyze_profiles:
                # 收集所有需要分析的论文 id（去重）
                hf_need = await get_hf_papers_need_detail(today)
                arxiv_need = await get_arxiv_papers_need_detail(today)

                hf_analyze_ids = set()
                arxiv_analyze_ids = set()
                for prof in analyze_profiles:
                    kw = prof.get("keywords", "")
                    for p in filter_papers_by_keywords(hf_need, kw):
                        hf_analyze_ids.add(p["id"])
                    for p in filter_papers_by_keywords(arxiv_need, kw):
                        arxiv_analyze_ids.add(p["id"])

                for paper in hf_need:
                    if paper["id"] not in hf_analyze_ids:
                        continue
                    try:
                        summary = await generate_detail(
                            paper["title"], paper.get("abstract", ""), arxiv_id=paper.get("arxiv_id")
                        )
                        await update_llm_summary(paper["id"], summary, "completed")
                        logger.info(f"Auto-fetch: HF detail done: {paper['title'][:50]}...")
                    except Exception as e:
                        logger.error(f"Auto-fetch: HF detail failed {paper['id']}: {e}")
                        await update_llm_summary(paper["id"], str(e), "failed")

                for paper in arxiv_need:
                    if paper["id"] not in arxiv_analyze_ids:
                        continue
                    try:
                        summary = await generate_detail(
                            paper["title"], paper.get("abstract", ""), arxiv_id=paper.get("arxiv_id")
                        )
                        await update_arxiv_llm_summary(paper["id"], summary, "completed")
                        logger.info(f"Auto-fetch: ArXiv detail done: {paper['title'][:50]}...")
                    except Exception as e:
                        logger.error(f"Auto-fetch: ArXiv detail failed {paper['id']}: {e}")
                        await update_arxiv_llm_summary(paper["id"], str(e), "failed")

            logger.info(f"Auto-fetch: completed, next in {interval} min")
            await asyncio.sleep(interval * 60)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Auto-fetch loop error: {e}")
            await asyncio.sleep(60)
