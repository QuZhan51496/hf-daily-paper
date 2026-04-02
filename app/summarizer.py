import asyncio
import logging
from openai import AsyncOpenAI
from app.config import load_config
from app.database import update_llm_summary, update_brief_summary

logger = logging.getLogger(__name__)

BRIEF_PROMPT = """用中文1-2句话概括这篇论文的核心工作。严格要求：
- 不超过120个字
- 禁止分段、换行、列举、使用标号
- 禁止任何前缀（如"本文"、"该论文"开头可以，但不要"概要："等标签）
- 不要解释方法细节，只说研究了什么、做了什么"""

DETAIL_PROMPT = """你是一位专业的AI研究论文分析专家。请为给定的论文生成全面的中文分析，不限篇幅。

请按以下结构组织内容：
1. **研究问题**：该论文要解决什么问题？
2. **创新点**：论文提出了哪些新的思路、方法或框架？
3. **方法详解**：详细介绍论文的核心方法和技术路线。
4. **实验结果**：简要概括主要实验结论和性能表现。
5. **总结**：一句话总结论文的核心贡献和价值。

面向技术读者，语言清晰准确，介绍和方法部分着重展开，实验部分可以精简。"""


def _get_client() -> AsyncOpenAI:
    config = load_config()
    return AsyncOpenAI(api_key=config.llm_api_key, base_url=config.llm_base_url)


async def generate_brief(title: str, abstract: str) -> str:
    config = load_config()
    client = _get_client()
    response = await client.chat.completions.create(
        model=config.llm_model,
        messages=[
            {"role": "system", "content": BRIEF_PROMPT},
            {"role": "user", "content": f"论文标题: {title}\n\n摘要: {abstract}"},
        ],
        max_tokens=100,
        temperature=0.2,
    )
    return response.choices[0].message.content


async def generate_detail(title: str, abstract: str, arxiv_id: str | None = None) -> str:
    config = load_config()
    client = _get_client()
    user_msg = f"论文标题: {title}\n\n摘要: {abstract}"

    if arxiv_id:
        from app.paper_content import fetch_paper_content
        content, source = await fetch_paper_content(arxiv_id)
        if content:
            user_msg += f"\n\n论文全文（来源: {source}）:\n{content}"
            logger.info(f"Detail analysis using {source} content for {arxiv_id}")
        else:
            logger.info(f"No full content available for {arxiv_id}, using abstract only")

    response = await client.chat.completions.create(
        model=config.llm_model,
        messages=[
            {"role": "system", "content": DETAIL_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content


async def generate_briefs_batch(papers: list[dict]):
    """抓取论文后批量生成极简概要（主页用），无并发限制"""

    async def _process(paper: dict):
        try:
            summary = await generate_brief(paper["title"], paper.get("abstract", ""))
            await update_brief_summary(paper["id"], summary, "completed")
            logger.info(f"Brief done: {paper['title'][:50]}...")
        except Exception as e:
            logger.error(f"Brief failed for paper {paper['id']}: {e}")
            await update_brief_summary(paper["id"], str(e), "failed")

    await asyncio.gather(*[_process(p) for p in papers])
