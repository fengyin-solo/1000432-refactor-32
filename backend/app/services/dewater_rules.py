"""脱水运行判定口径：状态序列、开停机动作映射、异常与统计规则的唯一来源。

服务层（app.services.dewater）、接口层（app.routers.dewater）、仓库统计
（app.store.overview）都从这里取口径，避免列表与概览各写一遍、互相打架。
"""
from __future__ import annotations

from typing import Any, Mapping

MODULE = "dewater"

# 登记必填字段：缺了要在接口层说明，而不是静默丢弃
REQUIRED_FIELDS = ["记录编号", "脱水机编号", "进泥量"]

# 状态序列：待开机 → 运行中 → 已停机 / 故障停机；序列最后一个为终态
STATUS_ORDER = ["待开机", "运行中", "已停机", "故障停机"]

# 开停机动作 → 目标状态。同一张表给服务层流转、接口层校验与前端动作栏共用
ACTION_RULES = {"确认开机": "运行中", "确认停机": "已停机", "登记故障": "故障停机"}

# 负向动作：执行后记录计入异常。故障停机是脱水运行唯一的负向流转，之前漏标了
NEGATIVE_ACTIONS = ["登记故障"]

# 异常状态：由负向动作流转而来，判定异常时认状态不认历史动作
ABNORMAL_STATUSES = [STATUS_ORDER[-1]]

# 表内自检：动作映射的目标状态必须落在状态序列里，负向动作必须映射到异常状态
assert all(target in STATUS_ORDER for target in ACTION_RULES.values()), "动作映射越出了状态序列"
assert all(ACTION_RULES[action] in ABNORMAL_STATUSES for action in NEGATIVE_ACTIONS), "负向动作没有对应异常状态"


def target_status(action: str) -> str | None:
    """动作对应的目标状态；动作不在表里时返回 None，由调用方给出说明。"""
    return ACTION_RULES.get(action)


def is_final_status(status: str) -> bool:
    """是否终态：进入终态后不再有待办。"""
    return status == STATUS_ORDER[-1]


def parse_inflow(entry: Mapping[str, Any]) -> float | None:
    """进泥量数值：缺失或不是数字时返回 None（样例文本不视为异常）。"""
    raw = entry.get("进泥量")
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def is_abnormal(entry: Mapping[str, Any]) -> bool:
    """异常口径（全系统唯一一份）：故障停机，或进泥量可解析且不为正数。"""
    if str(entry.get("status") or "") in ABNORMAL_STATUSES:
        return True
    inflow = parse_inflow(entry)
    return inflow is not None and inflow <= 0


def summarize(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """脱水运行统计口径：列表页统计卡片与运营概览共用这一份。"""
    running_units = {row.get("脱水机编号") for row in rows if row.get("status") == "运行中"}
    running_units.discard(None)
    return {
        "total": len(rows),
        "pending": sum(1 for row in rows if row.get("pending")),
        "abnormal": sum(1 for row in rows if is_abnormal(row)),
        "running_units": len(running_units),
    }
