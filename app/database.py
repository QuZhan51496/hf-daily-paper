import json
import aiosqlite
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent.parent / "data" / "papers.db"


async def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                arxiv_id TEXT NOT NULL,
                date TEXT NOT NULL,
                title TEXT NOT NULL,
                abstract TEXT,
                hf_ai_summary TEXT,
                llm_summary TEXT,
                llm_summary_status TEXT DEFAULT 'pending',
                authors TEXT,
                keywords TEXT,
                upvotes INTEGER DEFAULT 0,
                num_comments INTEGER DEFAULT 0,
                thumbnail_url TEXT,
                github_repo TEXT,
                github_stars INTEGER,
                project_page TEXT,
                published_at TEXT,
                submitted_daily_at TEXT,
                created_at TEXT,
                brief_summary TEXT,
                brief_summary_status TEXT DEFAULT 'pending',
                UNIQUE(arxiv_id, date)
            );

            CREATE TABLE IF NOT EXISTS fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE NOT NULL,
                fetched_at TEXT NOT NULL,
                paper_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'success',
                error_message TEXT
            );

            CREATE TABLE IF NOT EXISTS arxiv_papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                arxiv_id TEXT NOT NULL,
                date TEXT NOT NULL,
                title TEXT NOT NULL,
                abstract TEXT,
                authors TEXT,
                categories TEXT,
                primary_category TEXT,
                published_at TEXT,
                updated_at TEXT,
                brief_summary TEXT,
                brief_summary_status TEXT DEFAULT 'pending',
                llm_summary TEXT,
                llm_summary_status TEXT DEFAULT 'pending',
                created_at TEXT,
                UNIQUE(arxiv_id, date)
            );

            CREATE TABLE IF NOT EXISTS arxiv_fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                paper_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'success',
                error_message TEXT,
                UNIQUE(category, date)
            );

            CREATE TABLE IF NOT EXISTS keyword_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                keywords TEXT NOT NULL,
                categories TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT
            );
        """)

        # migrations
        for table, col, default in [
            ("papers", "brief_summary", None),
            ("papers", "brief_summary_status", "'pending'"),
            ("keyword_profiles", "categories", "''"),
        ]:
            try:
                ddl = f"ALTER TABLE {table} ADD COLUMN {col} TEXT"
                if default:
                    ddl += f" DEFAULT {default}"
                await db.execute(ddl)
                await db.commit()
            except Exception:
                pass


async def get_db():
    return aiosqlite.connect(DB_PATH)


async def insert_papers(date: str, papers: list[dict]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        count = 0
        for p in papers:
            try:
                changes_before = db.total_changes
                await db.execute(
                    """INSERT OR IGNORE INTO papers
                    (arxiv_id, date, title, abstract, hf_ai_summary, authors, keywords,
                     upvotes, num_comments, thumbnail_url, github_repo, github_stars,
                     project_page, published_at, submitted_daily_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        p["arxiv_id"], date, p["title"], p["abstract"],
                        p.get("hf_ai_summary"), json.dumps(p.get("authors", []), ensure_ascii=False),
                        json.dumps(p.get("keywords", []), ensure_ascii=False),
                        p.get("upvotes", 0), p.get("num_comments", 0),
                        p.get("thumbnail_url"), p.get("github_repo"),
                        p.get("github_stars"), p.get("project_page"),
                        p.get("published_at"), p.get("submitted_daily_at"), now,
                    ),
                )
                if db.total_changes > changes_before:
                    count += 1
            except Exception:
                pass
        await db.commit()

        await db.execute(
            "INSERT OR REPLACE INTO fetch_log (date, fetched_at, paper_count, status) VALUES (?, ?, ?, ?)",
            (date, now, count, "success"),
        )
        await db.commit()
    return count


async def get_papers_by_date(date: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM papers WHERE date = ? ORDER BY upvotes DESC", (date,)
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]


async def get_paper_detail(arxiv_id: str, date: str | None = None) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if date:
            cursor = await db.execute(
                "SELECT * FROM papers WHERE arxiv_id = ? AND date = ?", (arxiv_id, date)
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM papers WHERE arxiv_id = ? ORDER BY date DESC LIMIT 1", (arxiv_id,)
            )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def get_available_dates() -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT DISTINCT date FROM papers ORDER BY date DESC"
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


async def is_date_fetched(date: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM fetch_log WHERE date = ? AND status = 'success'", (date,)
        )
        return await cursor.fetchone() is not None


async def update_llm_summary(paper_id: int, summary: str, status: str = "completed"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE papers SET llm_summary = ?, llm_summary_status = ? WHERE id = ?",
            (summary, status, paper_id),
        )
        await db.commit()


async def update_brief_summary(paper_id: int, summary: str, status: str = "completed"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE papers SET brief_summary = ?, brief_summary_status = ? WHERE id = ?",
            (summary, status, paper_id),
        )
        await db.commit()


async def get_pending_papers(date: str | None = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if date:
            cursor = await db.execute(
                "SELECT * FROM papers WHERE llm_summary_status IN ('pending', 'failed') AND date = ?",
                (date,),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM papers WHERE llm_summary_status IN ('pending', 'failed')"
            )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]


async def get_paper_by_id(paper_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


# ── ArXiv papers ──────────────────────────────────────────────

async def insert_arxiv_papers(date: str, category: str, papers: list[dict]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        count = 0
        for p in papers:
            try:
                changes_before = db.total_changes
                await db.execute(
                    """INSERT OR IGNORE INTO arxiv_papers
                    (arxiv_id, date, title, abstract, authors, categories,
                     primary_category, published_at, updated_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        p["arxiv_id"], date, p["title"], p.get("abstract", ""),
                        json.dumps(p.get("authors", []), ensure_ascii=False),
                        json.dumps(p.get("categories", []), ensure_ascii=False),
                        p.get("primary_category", ""),
                        p.get("published_at"), p.get("updated_at"), now,
                    ),
                )
                if db.total_changes > changes_before:
                    count += 1
            except Exception:
                pass
        await db.commit()
        await db.execute(
            "INSERT OR REPLACE INTO arxiv_fetch_log (category, date, fetched_at, paper_count, status) VALUES (?, ?, ?, ?, ?)",
            (category, date, now, count, "success"),
        )
        await db.commit()
    return count


async def get_arxiv_papers_by_date(date: str, category: str | None = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if category:
            cursor = await db.execute(
                "SELECT * FROM arxiv_papers WHERE date = ? AND primary_category = ? ORDER BY title",
                (date, category),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM arxiv_papers WHERE date = ? ORDER BY title", (date,)
            )
        rows = await cursor.fetchall()
        return [_arxiv_row_to_dict(r) for r in rows]


async def get_arxiv_paper_detail(arxiv_id: str, date: str | None = None) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if date:
            cursor = await db.execute(
                "SELECT * FROM arxiv_papers WHERE arxiv_id = ? AND date = ?", (arxiv_id, date)
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM arxiv_papers WHERE arxiv_id = ? ORDER BY date DESC LIMIT 1", (arxiv_id,)
            )
        row = await cursor.fetchone()
        return _arxiv_row_to_dict(row) if row else None


async def get_arxiv_paper_by_id(paper_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM arxiv_papers WHERE id = ?", (paper_id,))
        row = await cursor.fetchone()
        return _arxiv_row_to_dict(row) if row else None


async def get_arxiv_available_dates(category: str | None = None) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        if category:
            cursor = await db.execute(
                "SELECT DISTINCT date FROM arxiv_papers WHERE primary_category = ? ORDER BY date DESC",
                (category,),
            )
        else:
            cursor = await db.execute("SELECT DISTINCT date FROM arxiv_papers ORDER BY date DESC")
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


async def update_arxiv_brief_summary(paper_id: int, summary: str, status: str = "completed"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE arxiv_papers SET brief_summary = ?, brief_summary_status = ? WHERE id = ?",
            (summary, status, paper_id),
        )
        await db.commit()


async def update_arxiv_llm_summary(paper_id: int, summary: str, status: str = "completed"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE arxiv_papers SET llm_summary = ?, llm_summary_status = ? WHERE id = ?",
            (summary, status, paper_id),
        )
        await db.commit()


# ── Keyword profiles ──────────────────────────────────────────

async def get_keyword_profiles() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM keyword_profiles ORDER BY name")
        return [dict(r) for r in await cursor.fetchall()]


async def get_keyword_profile(profile_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM keyword_profiles WHERE id = ?", (profile_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def create_keyword_profile(name: str, keywords: str, categories: str = "") -> int:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO keyword_profiles (name, keywords, categories, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (name, keywords, categories, now, now),
        )
        await db.commit()
        return cursor.lastrowid


async def update_keyword_profile(profile_id: int, name: str, keywords: str, categories: str = ""):
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE keyword_profiles SET name = ?, keywords = ?, categories = ?, updated_at = ? WHERE id = ?",
            (name, keywords, categories, now, profile_id),
        )
        await db.commit()


async def delete_keyword_profile(profile_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM keyword_profiles WHERE id = ?", (profile_id,))
        await db.commit()


# ── Helpers ───────────────────────────────────────────────────

def _row_to_dict(row) -> dict:
    d = dict(row)
    for key in ("authors", "keywords"):
        if d.get(key):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                d[key] = []
        else:
            d[key] = []
    return d


def _arxiv_row_to_dict(row) -> dict:
    d = dict(row)
    for key in ("authors", "categories"):
        if d.get(key):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                d[key] = []
        else:
            d[key] = []
    return d
