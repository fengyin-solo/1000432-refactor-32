"""脱水运行业务规则：列表筛选、登记校验与开停机流转的流程编排。

状态序列、动作映射、异常与统计口径统一收在 app.services.dewater_rules，
这里只编排流程，不再各自维护一份判定。
"""
from __future__ import annotations

from typing import Any

from app.services import dewater_rules as rules
from app.store import store


class DewaterService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(rules.MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("记录编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._with_flags(row) for row in rows[start:start + size]], total

    def _with_flags(self, row: dict[str, Any]) -> dict[str, Any]:
        """列表行实时带上统一判定的异常标记，保证列表与统计同口径。"""
        return {**row, "abnormal": rules.is_abnormal(row)}

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(rules.MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in rules.REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(rules.MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in rules.REQUIRED_FIELDS})
        entry["status"] = rules.STATUS_ORDER[0]
        entry["pending"] = True
        store.append(rules.MODULE, entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(rules.MODULE, entry_id)
        if entry is None:
            return None, f"脱水记录 {entry_id} 不存在或已归档"
        target = rules.target_status(action)
        if target is None:
            return None, f"动作「{action}」不属于脱水运行可执行范围"
        current = str(entry.get("status") or "")
        if current == target:
            return None, f"脱水记录 {entry_id} 已是「{target}」，无需重复{action}"
        entry["status"] = target
        entry["pending"] = not rules.is_final_status(target)
        store.save()
        return entry, f"脱水记录已{action}"

    def summary(self) -> dict[str, Any]:
        """脱水运行统计：口径与运营概览一致；没有记录时给出说明。"""
        stats = rules.summarize(store.rows(rules.MODULE))
        cards = [
            {"label": "运行机组", "value": stats["running_units"]},
            {"label": "待处理记录", "value": stats["pending"]},
            {"label": "异常记录", "value": stats["abnormal"]},
        ]
        message = "" if stats["total"] else "暂无脱水运行记录，登记后统计会自动更新"
        return {**stats, "cards": cards, "message": message}
