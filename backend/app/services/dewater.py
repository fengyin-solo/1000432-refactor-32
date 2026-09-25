"""脱水运行业务规则：状态判定与异常口径的唯一来源。

状态流转、同机开停机互斥、进泥量异常判定、列表/概览统计都走这里，
路由层与前端只做展示，不再各自实现一份判定。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "dewater"
REQUIRED_FIELDS = ["记录编号", "脱水机编号", "进泥量"]
KEYWORD_FIELD = "记录编号"
MACHINE_FIELD = "脱水机编号"
FEED_FIELD = "进泥量"
MOISTURE_FIELD = "出泥含水率"
DURATION_FIELD = "运行时长"

# 状态序列与动作映射只有这一份，列表/动作/前端元数据都从这里取。
STATUS_ORDER = ["待开机", "运行中", "已停机", "故障停机"]
ACTION_RULES = {"确认开机": "运行中", "确认停机": "已停机", "登记故障": "故障停机"}
# 负向动作：执行后记录进入异常口径。故障停机必须算在内，不能漏。
NEGATIVE_ACTIONS = ["登记故障"]

# 每个动作只允许从哪些状态发起；不满足就拦下并说明当前状态，
# 重复开机/重复停机因此有了明确口径而不是被静默覆盖。
ACTION_ALLOWED_FROM: dict[str, set[str]] = {
    "确认开机": {"待开机"},
    "确认停机": {"运行中"},
    "登记故障": {"待开机", "运行中"},
}
TERMINAL_STATUSES = {"已停机", "故障停机"}

# 进泥量判定阈值（m³/批）：为空、非数值、不大于 0 或超过上限都算异常。
FEED_MIN = 0.0
FEED_MAX = 200.0


def _number(value: Any) -> float | None:
    """把字段值解析成数值；空白或非数值返回 None，不做任何隐式换算。"""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def feed_abnormal_reason(feed: Any) -> str | None:
    """进泥量异常口径：列表与概览共用这一个函数，不再各写一遍。

    返回 None 表示正常；返回字符串时既是异常标记依据，也是给用户的说明。
    """
    text = str(feed or "").strip()
    if not text:
        return "进泥量未记录，无法判定"
    amount = _number(text)
    if amount is None:
        return f"进泥量「{text}」不是有效数值"
    if amount <= FEED_MIN:
        return f"进泥量 {amount:g} 不大于 {FEED_MIN:g}，疑似停机或计量异常"
    if amount > FEED_MAX:
        return f"进泥量 {amount:g} 超过单批上限 {FEED_MAX:g}"
    return None


def classify_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """按统一口径刷新一条记录的 status/pending/abnormal/异常说明/运行状态。

    进泥量异常与故障停机任一成立即计入异常；返回的是同一条记录，方便链式使用。
    """
    status = str(entry.get("status") or STATUS_ORDER[0])
    if status not in STATUS_ORDER:
        status = STATUS_ORDER[0]
    entry["status"] = status

    reasons: list[str] = []
    if status == "故障停机":
        reasons.append("故障停机")
    feed_reason = feed_abnormal_reason(entry.get(FEED_FIELD))
    if feed_reason:
        reasons.append(feed_reason)

    entry["abnormal"] = bool(reasons)
    entry["pending"] = status not in TERMINAL_STATUSES
    entry["异常说明"] = "；".join(reasons)
    # 列表里的“运行状态”列直接展示统一状态，避免和真实 status 脱节。
    entry["运行状态"] = status
    return entry


class DewaterService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        machine: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [classify_entry(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get(KEYWORD_FIELD, ""))]
        if machine:
            rows = [row for row in rows if machine in str(row.get(MACHINE_FIELD, ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return classify_entry(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        rows = store.rows(MODULE)
        record_no = str(values[KEYWORD_FIELD]).strip()
        if any(str(row.get(KEYWORD_FIELD, "")).strip() == record_no for row in rows):
            return None, f"记录编号「{record_no}」已存在，请勿重复登记"
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in [
            KEYWORD_FIELD, MACHINE_FIELD, FEED_FIELD, MOISTURE_FIELD,
            "絮凝剂用量", DURATION_FIELD, "操作人员",
        ]:
            if str(values.get(field) or "").strip():
                entry[field] = str(values[field]).strip()
        entry["status"] = STATUS_ORDER[0]
        classify_entry(entry)
        rows.append(entry)
        store.save(MODULE)
        return entry, ""

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            # 没有记录时给出明确说明，而不是含糊地报操作失败。
            return None, f"脱水记录 {entry_id} 不存在或已归档，无法执行「{action}」"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于脱水运行可执行范围"

        classify_entry(entry)
        current = str(entry["status"])
        if current not in ACTION_ALLOWED_FROM[action]:
            # 同一台机重复开机/重复停机会落到这里：说明当前状态，拒绝覆盖。
            machine = entry.get(MACHINE_FIELD, "?")
            return None, (
                f"脱水机 {machine} 当前为「{current}」，"
                f"不能重复执行「{action}」；该动作仅在"
                f"「{'、'.join(sorted(ACTION_ALLOWED_FROM[action]))}」状态下可执行"
            )

        if action == "确认开机":
            machine = str(entry[MACHINE_FIELD]).strip()
            for other in store.rows(MODULE):
                if other is entry:
                    continue
                if str(other.get(MACHINE_FIELD, "")).strip() == machine \
                        and classify_entry(other)["status"] == "运行中":
                    return None, (
                        f"脱水机 {machine} 已有运行中的记录"
                        f"（记录编号 {other.get(KEYWORD_FIELD)}），请先停机后再开机"
                    )

        entry["status"] = ACTION_RULES[action]
        classify_entry(entry)
        store.save(MODULE)
        return entry, f"脱水记录已{action}"

    def statistics(self) -> dict[str, Any]:
        """脱水运行统计：与列表、运营概览共用同一份分类结果，保证口径一致。"""
        rows = [classify_entry(row) for row in store.rows(MODULE)]
        running_machines = {
            str(row.get(MACHINE_FIELD, "")).strip()
            for row in rows if row["status"] == "运行中"
        }
        durations = [amount for value in (
            row.get(DURATION_FIELD) for row in rows if row["status"] == "运行中"
        ) if (amount := _number(value)) is not None]
        moistures = [amount for value in (
            row.get(MOISTURE_FIELD) for row in rows
        ) if (amount := _number(value)) is not None]
        abnormal = sum(1 for row in rows if row["abnormal"])
        return {
            "total": len(rows),
            "running": len(running_machines),
            "pending": sum(1 for row in rows if row["pending"]),
            "abnormal": abnormal,
            "feed_abnormal": sum(
                1 for row in rows if feed_abnormal_reason(row.get(FEED_FIELD))
            ),
            "running_duration": round(sum(durations), 2),
            "moisture_avg": round(sum(moistures) / len(moistures), 2) if moistures else None,
        }
