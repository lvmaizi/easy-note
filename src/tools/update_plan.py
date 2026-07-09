from src.plan import PlanState, VALID_STATUS
from src.tools.base import BaseTool, ToolParameter


class UpdatePlanTool(BaseTool):
    name = "update_plan"
    description = (
        "创建或修改当前任务的执行计划。传入完整 steps 数组，整体覆盖现有计划。"
        "用于：复杂问题开始时列出步骤；每完成一步把该步标 completed 并把下一步标 in_progress；"
        "发现遗漏或顺序错时重写整个 steps。"
    )
    parameters = [
        ToolParameter(
            name="steps",
            type="array",
            description=(
                "步骤列表。每项含 id（int，唯一）、title（str）、"
                "status（pending|in_progress|completed，默认 pending）。"
            ),
            required=True,
        ),
    ]

    def __init__(self, state: PlanState):
        super().__init__()
        self.state = state

    def execute(self, steps) -> str:
        try:
            validated = self._validate(steps)
        except ValueError as e:
            return f"Error: {e}"
        self.state.replace(validated)
        return f"Plan 已更新（{len(validated)} 步）。"

    @staticmethod
    def _validate(steps) -> list[dict]:
        if not isinstance(steps, list) or not steps:
            raise ValueError("steps 必须是非空数组")
        seen_ids = set()
        out = []
        for i, s in enumerate(steps):
            if not isinstance(s, dict):
                raise ValueError(f"steps[{i}] 必须是对象")
            sid = s.get("id")
            title = s.get("title")
            status = s.get("status", "pending")
            if not isinstance(sid, int):
                raise ValueError(f"steps[{i}].id 必须是整数")
            if sid in seen_ids:
                raise ValueError(f"steps[{i}].id={sid} 重复")
            seen_ids.add(sid)
            if not isinstance(title, str) or not title.strip():
                raise ValueError(f"steps[{i}].title 必须是非空字符串")
            if status not in VALID_STATUS:
                raise ValueError(
                    f"steps[{i}].status={status!r} 非法，必须是 "
                    f"{sorted(VALID_STATUS)} 之一"
                )
            out.append({"id": sid, "title": title.strip(), "status": status})
        return out
