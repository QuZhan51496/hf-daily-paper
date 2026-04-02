import json
from pathlib import Path
from pydantic import BaseModel

CONFIG_PATH = Path(__file__).parent.parent / "config.json"


class Settings(BaseModel):
    llm_api_key: str
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    server_host: str = "0.0.0.0"
    server_port: int = 8080


_settings: Settings | None = None


def load_config() -> Settings:
    global _settings
    if _settings is not None:
        return _settings
    if not CONFIG_PATH.exists():
        raise FileNotFoundError("config.json not found, run setup first")
    data = json.loads(CONFIG_PATH.read_text())
    _settings = Settings(**data)
    return _settings


def save_config(settings: Settings) -> None:
    global _settings
    CONFIG_PATH.write_text(json.dumps(settings.model_dump(), indent=2, ensure_ascii=False))
    _settings = settings
