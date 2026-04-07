# Daily Paper

自动抓取 [Hugging Face Daily Papers](https://huggingface.co/papers) 和 [arXiv](https://arxiv.org) 的 AI 论文，并使用 LLM 生成中文概要和深度分析。

## 功能

- 自动抓取 Hugging Face 和 arXiv 论文，翻页时自动同步新增论文
- 关键词 Profile 过滤：多用户各自定义关键词和 arXiv 分类，精准筛选论文
- LLM 生成一句话概要（首页）和深度分析（详情页）
- 深度分析自动获取论文全文（arXiv HTML / PDF），提升分析质量
- Markdown 渲染 + LaTeX 数学公式支持
- 网页端 API 配置，支持任意 OpenAI 兼容接口

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动服务

```bash
python run.py
```

浏览器访问 `http://localhost:8080`，首次使用点击右上角「设置」配置 LLM API 信息和关键词 Profile。

### 配置说明

在设置页面填写：

- **API Base URL** — OpenAI 兼容接口地址（如 `https://api.openai.com/v1`）
- **API Key** — 接口密钥
- **模型名称** — 使用的模型（如 `gpt-4o-mini`）
- **关键词 Profile** — 定义名称、关键词和 arXiv 分类，用于过滤论文

## 技术栈

- **后端**: FastAPI + SQLite (aiosqlite)
- **前端**: Jinja2 模板 + vanilla JavaScript
- **LLM**: OpenAI 兼容 API
- **论文全文**: arXiv HTML (BeautifulSoup) / PDF (PyMuPDF)
- **渲染**: marked.js (Markdown) + KaTeX (LaTeX)

## 项目结构

```
daily-paper/
├── run.py                  # 入口脚本
├── requirements.txt        # Python 依赖
├── config.json             # API 配置（自动生成）
├── data/                   # SQLite 数据库
├── app/
│   ├── main.py             # FastAPI 应用
│   ├── config.py           # 配置管理
│   ├── database.py         # 数据库操作
│   ├── fetcher.py          # HF API 抓取
│   ├── arxiv_fetcher.py    # arXiv API 抓取
│   ├── keyword_matcher.py  # 关键词匹配过滤
│   ├── summarizer.py       # LLM 概要/分析生成
│   ├── paper_content.py    # arXiv 全文获取
│   ├── models.py           # Pydantic 模型
│   └── routers/
│       ├── api.py          # API 路由
│       └── pages.py        # 页面路由
├── templates/              # Jinja2 模板
└── static/                 # CSS / JS
```

---

Powered by [Claude Code](https://claude.ai/code)
