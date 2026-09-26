"""运输委托接口：维护运输委托单，覆盖受理委托、开始运输、关闭委托、退回待受理与修改约定。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.order import OrderService

router = APIRouter(prefix="/api/order", tags=["运输委托"])

service = OrderService()

LIST_FIELDS = ["委托编号", "委托方", "起运地址", "到达地址", "货物品名", "温层要求", "装载方量", "托运状态"]
STATUSES = ["待受理", "已受理", "运输中", "已关闭"]


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
    """导出运输委托清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "order", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条运输委托单明细（含流转记录）；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"运输委托单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条运输委托单：委托编号重复当场拦下，缺字段时说明缺的是哪一项。"""
    entry, message = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="运输委托单已登记，进入待受理", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条运输委托单执行受理、开始运输、关闭或退回待受理；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    operator = str(payload.values.get("operator") or "").strip()
    reason = str(payload.values.get("reason") or payload.remark or "").strip()
    entry, message = service.run_action(entry_id, action, operator, reason)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/update", response_model=ActionResult)
def update_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """修改委托内容：温层要求、装载方量仅在待受理状态可改，其余状态须先退回并写清原因。"""
    operator = str(payload.values.get("operator") or "").strip()
    entry, message = service.update_entry(entry_id, payload.values, operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
