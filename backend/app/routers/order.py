"""运输委托接口：维护运输委托单，覆盖登记、受理、运输、退回、关闭与资料变更。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.order import STATUS_ORDER, OrderService

router = APIRouter(prefix="/api/order", tags=["运输委托"])

service = OrderService()

LIST_FIELDS = [
    "委托编号", "委托方", "起运地址", "到达地址", "货物品名",
    "温层要求", "装载方量", "托运状态", "最近经办人", "最近处理时间",
]
STATUSES = STATUS_ORDER


def _operator_of(payload: EntryPayload) -> str:
    """经办人优先取请求体里的 operator，其次 remark，便于前端直接传当前值班人。"""
    operator = str(payload.values.pop("operator", "") or payload.remark or "").strip()
    return operator


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按委托编号检索"),
    status: str | None = Query(default=None, description="待受理、已受理、运输中、已关闭"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按委托编号与托运状态过滤运输委托列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出运输委托清单：返回全量数据（含流转记录）。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "order", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条运输委托单明细与完整流转记录；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"运输委托单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条运输委托单；缺字段或委托编号重复时说明原因，不落库。"""
    operator = _operator_of(payload)
    entry, message = service.create_entry(payload.values, operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.put("/{entry_id}", response_model=ActionResult)
def update_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """变更委托资料；非待受理状态改温层要求或装载方量会被拦下，提示先退回。"""
    operator = _operator_of(payload)
    entry, message = service.update_entry(entry_id, payload.values, operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """受理、开始运输、退回待受理、关闭委托；退回必须带原因，关闭后不可再改动。"""
    action = str(payload.values.get("action") or "").strip()
    reason = str(payload.values.get("reason") or "").strip()
    operator = str(payload.values.get("operator") or payload.remark or "").strip()
    entry, message = service.run_action(entry_id, action, operator, reason)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
