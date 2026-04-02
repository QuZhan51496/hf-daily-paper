from pydantic import BaseModel


class PaperResponse(BaseModel):
    id: int
    arxiv_id: str
    date: str
    title: str
    abstract: str | None = None
    hf_ai_summary: str | None = None
    llm_summary: str | None = None
    llm_summary_status: str = "pending"
    brief_summary: str | None = None
    brief_summary_status: str = "pending"
    authors: list[str] = []
    keywords: list[str] = []
    upvotes: int = 0
    num_comments: int = 0
    thumbnail_url: str | None = None
    github_repo: str | None = None
    github_stars: int | None = None
    project_page: str | None = None
    published_at: str | None = None
    arxiv_url: str = ""

    @classmethod
    def from_db(cls, row: dict) -> "PaperResponse":
        return cls(
            **row,
            arxiv_url=f"https://arxiv.org/abs/{row['arxiv_id']}",
        )


class SetupRequest(BaseModel):
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
