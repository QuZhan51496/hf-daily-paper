import logging
from pathlib import Path
import httpx
import fitz  # pymupdf

logger = logging.getLogger(__name__)

THUMBNAIL_DIR = Path(__file__).parent.parent / "data" / "thumbnails"
ARXIV_PDF_URL = "https://arxiv.org/pdf/{arxiv_id}"


async def get_thumbnail_path(arxiv_id: str) -> Path | None:
    """获取论文首页上半部分缩略图，有缓存直接返回，无则生成。"""
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = arxiv_id.replace("/", "_")
    cache_path = THUMBNAIL_DIR / f"{safe_name}.png"

    if cache_path.exists():
        return cache_path

    try:
        url = ARXIV_PDF_URL.format(arxiv_id=arxiv_id)
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning(f"PDF download failed for {arxiv_id}: {resp.status_code}")
                return None

        doc = fitz.open(stream=resp.content, filetype="pdf")
        page = doc[0]

        # 裁剪首页上半部分
        rect = page.rect
        clip = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1 / 2)

        # 渲染，zoom=2 提高清晰度
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat, clip=clip)

        pix.save(str(cache_path))
        doc.close()
        logger.info(f"Thumbnail generated for {arxiv_id}")
        return cache_path

    except Exception as e:
        logger.warning(f"Thumbnail generation failed for {arxiv_id}: {e}")
        return None
