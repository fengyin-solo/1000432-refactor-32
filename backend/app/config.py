"""运行配置：端口、跨域、运行环境。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    app_name: str = "污水处理厂工艺管控平台"
    env: str = "local"
    port: int = 8000
    # 运行记录落盘位置：刷新或重启后既有记录从这里恢复
    data_file: Path = BACKEND_ROOT / "data" / "store.json"
    allowed_origins: list[str] = field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )
    page_size_default: int = 20
    page_size_max: int = 200


settings = Settings()
