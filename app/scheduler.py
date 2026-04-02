import asyncio
import logging
from datetime import date
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.config import load_config
from app.fetcher import fetch_daily_papers
from app.database import insert_papers, is_date_fetched, get_papers_by_date
from app.summarizer import generate_briefs_batch

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(coro)
        else:
            loop.run_until_complete(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(coro)


async def fetch_and_summarize(target_date: str):
    logger.info(f"Starting fetch and summarize for {target_date}")
    try:
        papers = await fetch_daily_papers(target_date)
        if papers:
            await insert_papers(target_date, papers)
            all_papers = await get_papers_by_date(target_date)
            need_brief = [p for p in all_papers if p.get("brief_summary_status") != "completed"]
            if need_brief:
                await generate_briefs_batch(need_brief)
        logger.info(f"Completed processing for {target_date}: {len(papers)} papers")
    except Exception as e:
        logger.error(f"Error processing {target_date}: {e}")


def _daily_job():
    today = date.today().isoformat()
    _run_async(fetch_and_summarize(today))


def start_scheduler():
    global _scheduler
    config = load_config()
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _daily_job,
        CronTrigger(hour=config.fetch_hour, minute=config.fetch_minute),
        id="daily_fetch",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(f"Scheduler started: daily fetch at {config.fetch_hour:02d}:{config.fetch_minute:02d}")


def shutdown_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


async def backfill_today():
    today = date.today().isoformat()
    if not await is_date_fetched(today):
        logger.info(f"Backfilling today's papers: {today}")
        await fetch_and_summarize(today)
    else:
        all_papers = await get_papers_by_date(today)
        need_brief = [p for p in all_papers if p.get("brief_summary_status") != "completed"]
        if need_brief:
            logger.info(f"Resuming {len(need_brief)} pending briefs for {today}")
            await generate_briefs_batch(need_brief)
