"""脱水运行接口：维护脱水记录，覆盖确认开机、确认停机、登记故障等动作。

状态与异常判定全部来自 DewaterService，本层不重复实现任何业务口径。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services import dewater as rules
from app.services.dewater import DewaterService

router = APIRouter(prefix="/api/dewater", tags=["脱水运行"])

service = DewaterService()


@router.get("/meta")
def action_meta() -> dict[str, Any]:
    """暴露唯一一份状态/动作/阈值口径，前端按此渲染，不再各写一份。"""
    return {
        "statuses": rules.STATUS_ORDER,
        "actions": list(rules.ACTION_RULES),
        "action_targets": rules.ACTION_RULES,
        "action_allowed_from": {
            action: sorted(states) for action, states in rules.ACTION_ALLOWED_FROM.items()
        },
        "negative_actions": rules.NEGATIVE_ACTIONS,
        "feed_min": rules.FEED_MIN,
        "feed_max": rules.FEED_MAX,
    }


@router.get("/stats")
def stats() -> dict[str, Any]:
    """脱水运行概览卡片：统计口径与列表、运营概览共用 service。"""
    return service.statistics()


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    machine: str | None = Query(default=None, description="按脱水机编号检索"),
    status: str | None = Query(default=None, description="待开机、运行中、已停机、故障停机"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按记录编号、脱水机编号与状态过滤脱水运行列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword, machine=machine, status=status, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出脱水运行清单：返回统一分类口径下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "dewater", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条脱水记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"脱水记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条脱水记录，缺字段或编号重复时说明原因而不是静默丢弃。"""
    entry, message = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="脱水记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条脱水记录执行确认开机、确认停机、登记故障；没有记录、重复开停机都会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
