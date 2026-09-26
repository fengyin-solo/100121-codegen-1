"""运输委托业务规则：托运状态顺序流转、退回留痕、字段变更校验。

托运状态只在一条固定链路上单向前进：待受理 → 已受理 → 运输中；
已受理或运输中如需改温层要求、装载方量，必须先退回待受理并写明原因。
每次登记、流转、退回、关闭与资料变更都记入「流转记录」，含时间与经办人。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "order"

# 登记时缺一不可的字段；货物品名为空会在接口层明确报出缺项。
REQUIRED_FIELDS = ["委托编号", "委托方", "起运地址", "货物品名"]
# 受理之后允许调整的业务字段（仅在待受理状态下可改）。
EDIT_FIELDS = ["委托方", "起运地址", "到达地址", "货物品名", "温层要求", "装载方量"]
# 这两项变更影响运输安排，必须先退回待受理。
SENSITIVE_FIELDS = ["温层要求", "装载方量"]

STATUS_PENDING = "待受理"
STATUS_ACCEPTED = "已受理"
STATUS_TRANSPORTING = "运输中"
STATUS_CLOSED = "已关闭"
ACTIVE_STATUSES = [STATUS_PENDING, STATUS_ACCEPTED, STATUS_TRANSPORTING]
STATUS_ORDER = ACTIVE_STATUSES + [STATUS_CLOSED]

# 正向动作：动作名 -> (前置状态, 目标状态)，不允许跳步。
FORWARD_ACTIONS = {
    "受理委托": (STATUS_PENDING, STATUS_ACCEPTED),
    "开始运输": (STATUS_ACCEPTED, STATUS_TRANSPORTING),
}
RETURN_ACTION = "退回待受理"
CLOSE_ACTION = "关闭委托"

DEFAULT_OPERATOR = "未署名经办人"


def _now() -> str:
    """统一留痕时间口径，精确到秒。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class OrderService:
    # ---- 查询 ----------------------------------------------------------
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
            # 列表与详情都以「托运状态」为唯一口径，避免两处显示不一致。
            rows = [row for row in rows if row.get("托运状态") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    # ---- 登记 ----------------------------------------------------------
    def create_entry(
        self, values: dict[str, Any], operator: str
    ) -> tuple[dict[str, Any] | None, str]:
        missing = [
            field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()
        ]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}，请补全后再保存"

        code = str(values["委托编号"]).strip()
        # 同一个委托编号重复登记当场拦下。
        if any(str(row.get("委托编号") or "").strip() == code for row in store.rows(MODULE)):
            return None, f"委托编号「{code}」已登记过，不能重复登记，请核对原委托"

        operator = operator or DEFAULT_OPERATOR
        entry: dict[str, Any] = {
            "id": max((int(row.get("id", 0)) for row in store.rows(MODULE)), default=0) + 1,
        }
        for field in REQUIRED_FIELDS:
            entry[field] = str(values[field]).strip()
        for field in ["到达地址", "温层要求", "装载方量"]:
            entry[field] = str(values.get(field) or "").strip()
        entry["abnormal"] = False
        entry["流转记录"] = []
        self._apply_status(entry, STATUS_PENDING)
        self._append_history(
            entry,
            operator=operator,
            action="登记委托",
            from_status="",
            to_status=STATUS_PENDING,
        )
        store.rows(MODULE).append(entry)
        return entry, "运输委托单已登记，托运状态为待受理"

    # ---- 状态动作 -------------------------------------------------------
    def run_action(
        self,
        entry_id: int,
        action: str,
        operator: str = "",
        reason: str = "",
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"运输委托单 {entry_id} 不存在或已归档"
        current = str(entry.get("托运状态") or "")
        operator = operator or DEFAULT_OPERATOR
        reason = reason.strip()

        if current == STATUS_CLOSED:
            return None, "该委托已关闭，不能再做任何改动"

        if action in FORWARD_ACTIONS:
            required_status, target = FORWARD_ACTIONS[action]
            if current == target:
                return None, f"委托已处于「{target}」，无需重复{action}"
            if current != required_status:
                return None, (
                    f"当前托运状态为「{current}」，不能直接{action}；"
                    f"需先处于「{required_status}」，状态只能依次推进"
                )
            self._apply_status(entry, target)
            self._append_history(
                entry,
                operator=operator,
                action=action,
                from_status=current,
                to_status=target,
            )
            return entry, f"已{action}，托运状态变更为{target}"

        if action == RETURN_ACTION:
            if current == STATUS_PENDING:
                return None, "委托当前已是待受理，无需退回"
            if current not in (STATUS_ACCEPTED, STATUS_TRANSPORTING):
                return None, f"当前托运状态为「{current}」，不能退回待受理"
            if not reason:
                return None, "退回待受理必须写清退回原因，请补充后再提交"
            self._apply_status(entry, STATUS_PENDING)
            self._append_history(
                entry,
                operator=operator,
                action=RETURN_ACTION,
                from_status=current,
                to_status=STATUS_PENDING,
                reason=reason,
            )
            return entry, f"已退回待受理，原因：{reason}"

        if action == CLOSE_ACTION:
            if current not in ACTIVE_STATUSES:
                return None, f"当前托运状态为「{current}」，不能关闭委托"
            self._apply_status(entry, STATUS_CLOSED)
            self._append_history(
                entry,
                operator=operator,
                action=CLOSE_ACTION,
                from_status=current,
                to_status=STATUS_CLOSED,
                reason=reason,
            )
            return entry, "委托已关闭，关闭后不可再改动"

        return None, f"动作「{action}」不属于运输委托可执行范围"

    # ---- 资料变更 -------------------------------------------------------
    def update_entry(
        self,
        entry_id: int,
        values: dict[str, Any],
        operator: str = "",
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"运输委托单 {entry_id} 不存在或已归档"
        current = str(entry.get("托运状态") or "")
        if current == STATUS_CLOSED:
            return None, "该委托已关闭，资料不能再改动"

        changes = self._diff_fields(entry, values)
        if not changes:
            return None, "未检测到字段变更，无需保存"

        sensitive_hit = [c["字段"] for c in changes if c["字段"] in SENSITIVE_FIELDS]
        if current != STATUS_PENDING:
            if sensitive_hit:
                return None, (
                    f"当前托运状态为「{current}」，{ '、'.join(sensitive_hit) }不能直接修改；"
                    "请先将委托退回待受理并写清原因，再进行变更"
                )
            return None, f"当前托运状态为「{current}」，资料变更需先退回待受理后再修改"

        # 待受理状态下同样不允许把必填项清空。
        for change in changes:
            field = change["字段"]
            if field in REQUIRED_FIELDS and not str(change["新值"] or "").strip():
                return None, f"{field}不能为空，请补全后再保存"

        operator = operator or DEFAULT_OPERATOR
        for change in changes:
            entry[change["字段"]] = change["新值"]
        self._append_history(
            entry,
            operator=operator,
            action="资料变更",
            from_status=current,
            to_status=current,
            changes=changes,
        )
        return entry, f"已保存 {len(changes)} 项变更：{'、'.join(c['字段'] for c in changes)}"

    # ---- 内部工具 -------------------------------------------------------
    def _diff_fields(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> list[dict[str, str]]:
        changes: list[dict[str, str]] = []
        for field in EDIT_FIELDS:
            if field not in values:
                continue
            new_value = str(values.get(field) or "").strip()
            old_value = str(entry.get(field) or "").strip()
            if new_value != old_value:
                changes.append({"字段": field, "原值": old_value, "新值": new_value})
        return changes

    def _apply_status(self, entry: dict[str, Any], status: str) -> None:
        """status 与「托运状态」始终同步，列表和详情读到的是同一份状态。"""
        entry["托运状态"] = status
        entry["status"] = status
        entry["pending"] = status in (STATUS_PENDING, STATUS_ACCEPTED)

    def _append_history(
        self,
        entry: dict[str, Any],
        *,
        operator: str,
        action: str,
        from_status: str,
        to_status: str,
        reason: str = "",
        changes: list[dict[str, str]] | None = None,
    ) -> None:
        record: dict[str, Any] = {
            "时间": _now(),
            "经办人": operator or DEFAULT_OPERATOR,
            "动作": action,
            "原状态": from_status or "—",
            "新状态": to_status or "—",
            "退回原因": reason,
        }
        if changes:
            record["字段变更"] = [
                {"字段": c["字段"], "原值": c["原值"] or "（空）", "新值": c["新值"] or "（空）"}
                for c in changes
            ]
        entry.setdefault("流转记录", []).append(record)
        entry["最近经办人"] = record["经办人"]
        entry["最近处理时间"] = record["时间"]
