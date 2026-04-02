#!/usr/bin/env python3
"""HF Daily Paper - 入口脚本"""

import os

# 确保工作目录为项目根目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))


def main():
    host = "0.0.0.0"
    port = 8080

    print(f"\n启动服务器: http://{host}:{port}")
    print("按 Ctrl+C 停止\n")

    import uvicorn
    uvicorn.run(
        "app.main:create_app",
        host=host,
        port=port,
        factory=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
