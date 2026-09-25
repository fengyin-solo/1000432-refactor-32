"""数据仓库：内存表 + JSON 落盘，刷新或服务重启后既有运行记录不丢。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from app.config import settings
from app.seed import SEED_ROWS
from app.services.dewater_rules import MODULE as DEWATER_MODULE
from app.services.dewater_rules import is_abnormal as dewater_is_abnormal

# 各模块异常判定口径：有统一判定函数的模块用判定函数实时算，
# 其余模块仍读行上的 abnormal 标志
ABNORMAL_RESOLVERS: dict[str, Callable[[Mapping[str, Any]], bool]] = {
    DEWATER_MODULE: dewater_is_abnormal,
}


class Store:
    def __init__(self, data_file: Path | None = None) -> None:
        self._data_file = data_file
        self._tables: dict[str, list[dict[str, Any]]] = self._load()

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        """优先读落盘数据；文件不存在或损坏时回退示例数据，保证服务起得来。

        落盘数据里缺的模块（比如新上线的模块）用示例数据补齐。
        """
        tables: dict[str, list[dict[str, Any]]] = {}
        if self._data_file is not None and self._data_file.exists():
            try:
                data = json.loads(self._data_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = None
            if isinstance(data, dict):
                tables = {
                    str(name): [dict(row) for row in rows]
                    for name, rows in data.items()
                    if isinstance(rows, list)
                }
        for name, rows in SEED_ROWS.items():
            tables.setdefault(name, [dict(row) for row in rows])
        return tables

    def save(self) -> None:
        """把当前数据写回磁盘；每次变更后调用，刷新或重启后记录不丢。"""
        if self._data_file is None:
            return
        self._data_file.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._tables, ensure_ascii=False, indent=2)
        self._data_file.write_text(payload, encoding="utf-8")

    def append(self, module: str, row: dict[str, Any]) -> None:
        self.rows(module).append(row)
        self.save()

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
            resolver = ABNORMAL_RESOLVERS.get(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(
                    1 for row in rows
                    if (resolver(row) if resolver is not None else row.get("abnormal"))
                ),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store(settings.data_file)
