"""把 Agent 的进度事件转成 Qt 信号，供 GUI 实时展示。

GuiReporter 暴露 AgentLoop 进度回调所需的同名方法（鸭子类型调用）；
它不打印到控制台，而是 emit 一个 `event(kind, text)` 信号到主线程，
由 ChatWindow 渲染成「思考中…」「检索 notes」「已保存笔记」等活动轨迹。

AgentLoop 在后台线程调用这些方法，信号经 Qt 队列连接安全地投递到 UI 线程。
"""

import re

from PySide6.QtCore import QObject, Signal


class GuiReporter(QObject):
    # kind 取值：thinking / thinking_done / tool / plan，由 ChatWindow 分流渲染
    event = Signal(str, str)

    # ---- AgentLoop 进度回调接口（GUI 里大多为空实现或转信号）----

    def start(self, user_input: str) -> None:  # noqa: D401 - 接口对齐
        pass

    def turn_begin(self) -> None:
        pass

    def thinking(self) -> None:
        self.event.emit("thinking", "思考中…")

    def thinking_done(self) -> None:
        self.event.emit("thinking_done", "")

    def tools_parsed(self, count: int) -> None:
        if count > 0:
            self.event.emit("tool", f"准备调用 {count} 个工具…")

    def tool_executed(self, name: str, params: dict, result: str) -> None:
        self.event.emit("tool", self._describe(name, params, result))

    def final_answer(self) -> None:
        pass

    def summary(self) -> None:
        pass

    def plan_changed(self, plan) -> None:
        """update_plan 触发后由 PlanState observer 调用。"""
        if plan.is_empty():
            return
        marks = {"pending": "○", "in_progress": "◐", "completed": "●"}
        lines = [f"{marks.get(s.status, '○')} {s.title}" for s in plan.steps]
        self.event.emit("plan", "任务计划\n" + "\n".join(lines))

    # ---- 把工具调用描述成一句友好中文（无 ANSI，供 GUI 显示）----

    def _describe(self, name: str, params: dict, result: str) -> str:
        if result.startswith("Error:"):
            brief = result[len("Error:"):].strip()[:120].replace("\n", " ")
            return f"⚠ {name} 出错：{brief}"

        if name == "write_note":
            title = (params.get("title") or "").strip()
            m = re.search(r"已保存到 (.+?)(?:（标题|$)", result)
            path = m.group(1).strip() if m else ""
            tail = f"（{title}）" if title else ""
            if path:
                return f"📝 已保存笔记 → {path}{tail}"
            return f"📝 已保存笔记{tail}"

        if name == "search_files":
            q = (params.get("pattern") or "").strip()
            m = re.search(r"找到 (\d+) 个相关文件", result)
            if m:
                return f"🔍 检索「{q}」→ 命中 {m.group(1)} 个文件"
            if "未找到" in result:
                return f"🔍 检索「{q}」→ 未命中"
            return f"🔍 检索「{q}」"

        if name == "read_file":
            path = self._basename(params.get("file_path", ""))
            m = re.search(r"of (\d+) total", result) or re.search(r"(\d+) total", result)
            if m:
                return f"📄 读取 {path}（{m.group(1)} 行）"
            return f"📄 读取 {path}"

        if name == "list_directory":
            path = self._basename(params.get("directory", ""))
            return f"📁 浏览目录 {path or '.'}"

        if name == "update_plan":
            return "🗂 更新任务计划"

        return name

    @staticmethod
    def _basename(path: str) -> str:
        if not path:
            return ""
        return path.replace("\\", "/").rstrip("/").split("/")[-1] or path
