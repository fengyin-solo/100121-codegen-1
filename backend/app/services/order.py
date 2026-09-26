"""运输委托业务规则：状态流转、字段校验与筛选口径都收在这里。

流转约定：待受理 → 已受理 → 运输中 → 已关闭。
温层要求、装载方量属于关键约定，只有在待受理状态下才允许修改；
要改必须先把委托退回待受理并写清原因。每一次变更都记入流转记录（时间 + 经办人），
已关闭的委托一律拒绝改动。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "order"

# 登记时缺一不可；货物品名缺失要当场说明缺的是哪一项
REQUIRED_FIELDS = ["委托编号", "委托方", "起运地址", "到达地址", "货物品名"]
# 登记后允许修改的字段（委托编号是去重依据，不允许改）
EDITABLE_FIELDS = ["委托方", "起运地址", "到达地址", "货物品名", "温层要求", "装载方量"]
# 关键约定字段：仅待受理状态可改，其余状态须先退回待受理
GUARDED_FIELDS = ["温层要求", "装载方量"]

STATUS_ORDER = ["待受理", "已受理", "运输中", "已关闭"]
CLOSED_STATUS = "已关闭"
RETURN_ACTION = "退回待受理"
# 正向动作 -> (来源状态, 目标状态)，必须依次流转，不允许跳步
ACTION_RULES = {
    "受理委托": ("待受理", "已受理"),
    "开始运输": ("已受理", "运输中"),
    "关闭委托": ("运输中", "已关闭"),
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _record(entry: dict[str, Any], action: str, operator: str, detail: str) -> None:
    """每次变更都留痕：时间、经办人、动作、说明。"""
    entry.setdefault("history", []).append({
        "时间": _now(),
        "经办人": operator,
        "动作": action,
        "说明": detail,
    })


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    """列表、详情、动作回包都走这一个出口，保证各处看到的托运状态一致。"""
    data = dict(row)
    data["托运状态"] = str(row.get("status") or STATUS_ORDER[0])
    data["流转记录"] = [dict(item) for item in row.get("history", [])]
    return data


class OrderService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("委托编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [_serialize(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return _serialize(row) if row is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        code = str(values["委托编号"]).strip()
        for row in store.rows(MODULE):
            if str(row.get("委托编号", "")).strip() == code:
                return None, f"委托编号 {code} 已登记过，重复登记当场拦下"
        operator = str(values.get("operator") or "").strip()
        if not operator:
            return None, "缺少经办人：每次变更都要记下是谁处理的"
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS + GUARDED_FIELDS:
            entry[field] = str(values.get(field) or "").strip()
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["history"] = []
        _record(entry, "登记委托", operator, "运输委托登记，进入待受理")
        rows.append(entry)
        return _serialize(entry), ""

    def run_action(
        self,
        entry_id: int,
        action: str,
        operator: str,
        reason: str,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"运输委托单 {entry_id} 不存在或已归档"
        if entry.get("status") == CLOSED_STATUS:
            return None, f"运输委托单 {entry_id} 已关闭，不能再改动"
        if not operator:
            return None, "缺少经办人：每次变更都要记下是谁处理的"
        if action == RETURN_ACTION:
            return self._return_to_pending(entry, operator, reason)
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于运输委托可执行范围"
        source, target = ACTION_RULES[action]
        current = str(entry.get("status") or STATUS_ORDER[0])
        if current != source:
            return None, f"当前状态为「{current}」，须处于「{source}」才能执行「{action}」"
        entry["status"] = target
        entry["pending"] = target != CLOSED_STATUS
        if action == "受理委托":
            entry["abnormal"] = False
        _record(entry, action, operator, f"{source} → {target}")
        return _serialize(entry), f"运输委托单已{action}"

    def update_entry(
        self,
        entry_id: int,
        values: dict[str, Any],
        operator: str,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"运输委托单 {entry_id} 不存在或已归档"
        if entry.get("status") == CLOSED_STATUS:
            return None, f"运输委托单 {entry_id} 已关闭，不能再改动"
        if not operator:
            return None, "缺少经办人：每次变更都要记下是谁处理的"
        changes: dict[str, tuple[str, str]] = {}
        for field in EDITABLE_FIELDS:
            if field not in values:
                continue
            new_val = str(values.get(field) or "").strip()
            if field == "货物品名" and not new_val:
                return None, "缺少必填字段：货物品名"
            old_val = str(entry.get(field) or "")
            if new_val != old_val:
                changes[field] = (old_val, new_val)
        if not changes:
            return None, "没有需要保存的修改"
        guarded = [field for field in changes if field in GUARDED_FIELDS]
        current = str(entry.get("status") or STATUS_ORDER[0])
        if guarded and current != STATUS_ORDER[0]:
            return None, f"{'、'.join(guarded)}只能在待受理状态修改，请先退回待受理并写清原因"
        for field, (_, new_val) in changes.items():
            entry[field] = new_val
        detail = "；".join(f"{field}:{old or '空'}→{new or '空'}" for field, (old, new) in changes.items())
        _record(entry, "修改委托", operator, detail)
        return _serialize(entry), f"运输委托单已更新：{detail}"

    def _return_to_pending(
        self,
        entry: dict[str, Any],
        operator: str,
        reason: str,
    ) -> tuple[dict[str, Any] | None, str]:
        current = str(entry.get("status") or STATUS_ORDER[0])
        if current == STATUS_ORDER[0]:
            return None, "委托已处于待受理状态，无需退回"
        if not reason:
            return None, "退回待受理必须写清原因"
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = True
        _record(entry, RETURN_ACTION, operator, f"{current} → 待受理；原因：{reason}")
        return _serialize(entry), f"运输委托单已退回待受理，原因：{reason}"
