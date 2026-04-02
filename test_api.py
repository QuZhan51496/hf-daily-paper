"""快速测试 LLM API 连接"""
import json
from pathlib import Path
from openai import OpenAI

config = json.loads(Path("config.json").read_text())
print(f"Base URL: {config['llm_base_url']}")
print(f"Model:    {config['llm_model']}")
print(f"API Key:  {config['llm_api_key'][:8]}...{config['llm_api_key'][-4:]}")
print()

client = OpenAI(api_key=config["llm_api_key"], base_url=config["llm_base_url"])
resp = client.chat.completions.create(
    model=config["llm_model"],
    messages=[{"role": "user", "content": "Say hello in one sentence."}],
    max_tokens=50,
)
print("Response:", resp.choices[0].message.content)
print("\nAPI 连接正常!")
