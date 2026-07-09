"""后台线程执行 Agent 主循环，避免阻塞 UI。

AgentLoop.run 是同步阻塞调用（内部会多轮请求 LLM / 跑工具），直接在主线程跑
会卡死界面。这里用 QThread 把单次 run 放到后台线程，完成或异常通过信号回主线程。
进度事件不走这里，而是由共享的 GuiReporter 在本线程 emit、经队列连接投递到 UI。
"""

from PySide6.QtCore import QThread, Signal

from src.agent.loop import AgentLoop


class AgentWorker(QThread):
    finished_ok = Signal(str)   # 最终回答
    failed = Signal(str)        # 错误信息

    def __init__(self, agent: AgentLoop, user_input: str, parent=None):
        super().__init__(parent)
        self._agent = agent
        self._user_input = user_input

    def request_stop(self) -> None:
        """请求协作式中止当前 run。在 AgentLoop 的下一个安全检查点生效。

        无法中断进行中的 HTTP 请求；最坏需等当前 LLM 调用返回（受 client 超时约束）。
        """
        self._agent.cancel()

    def run(self) -> None:
        try:
            answer = self._agent.run(self._user_input)
            self.finished_ok.emit(answer)
        except (ConnectionError, TimeoutError, RuntimeError) as e:
            self.failed.emit(str(e))
        except Exception as e:  # noqa: BLE001 - UI 兜底，避免线程内崩溃无人感知
            self.failed.emit(f"未预期的错误：{e}")
