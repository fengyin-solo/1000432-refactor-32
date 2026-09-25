"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
需要跨重启保留运行记录的模块（目前只有脱水运行）调用 save() 落盘到
backend/data/<模块名>.json，启动时若存在该文件则优先于示例数据加载，
这样刷新页面甚至重启服务后，既有运行记录都不会丢。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.seed import SEED_ROWS

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }
        self._load_persisted()

    def _load_persisted(self) -> None:
        """启动时把已落盘模块的记录读回来；文件损坏时忽略，回退到示例数据。"""
        if not DATA_DIR.exists():
            return
        for path in sorted(DATA_DIR.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(payload, list):
                self._tables[path.stem] = [dict(row) for row in payload if isinstance(row, dict)]

    def save(self, module: str) -> None:
        """把某模块当前记录持久化到数据目录，保证刷新/重启后记录仍在。"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        target = DATA_DIR / f"{module}.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self.rows(module), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(target)

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
