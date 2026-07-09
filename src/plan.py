import logging
from dataclasses import dataclass, field
from typing import Callable, Literal, get_args

logger = logging.getLogger(__name__)

PlanStatus = Literal["pending", "in_progress", "completed"]
VALID_STATUS: frozenset[str] = frozenset(get_args(PlanStatus))


@dataclass
class PlanStep:
    id: int
    title: str
    status: PlanStatus = "pending"


@dataclass
class PlanState:
    steps: list[PlanStep] = field(default_factory=list)
    observers: list[Callable[["PlanState"], None]] = field(default_factory=list)

    def replace(self, raw_steps: list[dict]) -> None:
        """整体覆写。raw_steps 必须是已校验过的 dict 列表（校验由 UpdatePlanTool 负责）。"""
        self.steps = [PlanStep(**s) for s in raw_steps]
        self._notify()

    def clear(self) -> None:
        if not self.steps:
            return
        self.steps = []
        self._notify()

    def is_empty(self) -> bool:
        return not self.steps

    def all_completed(self) -> bool:
        return bool(self.steps) and all(s.status == "completed" for s in self.steps)

    def in_progress(self) -> "PlanStep | None":
        return next((s for s in self.steps if s.status == "in_progress"), None)

    def _notify(self) -> None:
        for cb in list(self.observers):  # 拷贝以防 callback 中途 mutate observers
            try:
                cb(self)
            except Exception as e:
                logger.exception("[plan observer error] %s", e)


_STATUS_MARK = {"pending": "☐", "in_progress": "◐", "completed": "☒"}


def render_plan_as_messages(plan: PlanState) -> list[dict]:
    """渲染当前 plan 为追加到 messages 末尾的临时段。

    返回值不进 ConversationContext，每轮重新生成。
    plan 为空时返回 []，不向对话注入任何内容。
    """
    if plan.is_empty():
        return []

    lines = ["[Current Plan]"]
    for s in plan.steps:
        lines.append(f"  {_STATUS_MARK[s.status]} {s.id}. {s.title}")

    in_prog = plan.in_progress()
    if in_prog:
        lines.append("")
        lines.append(
            f"[Hint] 当前进行中：第 {in_prog.id} 步「{in_prog.title}」。"
            "若已完成，请用 update_plan 推进；若发现遗漏或顺序需调整，"
            "可重写整个 steps 数组。"
        )

    return [{"role": "user", "content": "\n".join(lines)}]
