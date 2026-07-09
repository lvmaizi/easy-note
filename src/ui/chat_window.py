"""聊天主窗口：居中内容列 + 用户/助手消息 + 可折叠活动轨迹 + 自适应输入条。

设计目标（对标主流 AI 聊天客户端）
- 内容居中列：消息流约束在最大宽度内并水平居中，窗口再宽也不会把文字拉散。
- 助手消息为整列宽的文本块（头像 + 角色名 + Markdown 正文），不再是窄气泡。
- 工具调用收进可折叠的「思考与检索」轨迹：运行时展开并带动效，出结果后自动收起。
- 输入条为一个大圆角 composer，发送按钮内嵌右下角，随文本行数自适应高度。
- 运行中发送按钮变为「停止」按钮，可协作式中止当前请求；关窗时优雅等待后台线程退出。
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from typing import Callable

from src.agent.loop import AgentLoop
from src.config import AppConfig, load_config, save_settings
from src.ui.reporter import GuiReporter
from src.ui.settings_dialog import SettingsDialog
from src.ui.worker import AgentWorker

COLUMN_MAX_WIDTH = 820
USER_BUBBLE_MAX_WIDTH = 600

STYLE = """
* { font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei", sans-serif; }

QWidget#root { background: #F7F6F3; }

QWidget#header { background: #FFFFFF; border-bottom: 1px solid #ECE8E0; }
QLabel#logo {
    background: #2A6F6B; color: #FFFFFF; border-radius: 9px;
    font-size: 15px; min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px;
}
QLabel#title { color: #23211E; font-size: 15px; font-weight: 600; }
QLabel#subtitle { color: #A8A296; font-size: 12px; }

QPushButton#settingsBtn {
    background: transparent; border: 1px solid #ECE8E0; border-radius: 9px;
    color: #8A857C; font-size: 17px;
    min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px;
}
QPushButton#settingsBtn:hover { background: #F1EEE8; color: #2A6F6B; border-color: #DAD6CC; }
QPushButton#settingsBtn:disabled { color: #C2C0BA; border-color: #ECE8E0; }

QScrollArea { border: none; background: transparent; }
QWidget#chat { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 4px 2px; }
QScrollBar::handle:vertical { background: #DAD6CC; border-radius: 4px; min-height: 36px; }
QScrollBar::handle:vertical:hover { background: #C5C0B4; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QFrame#userBubble { background: #2A6F6B; border-radius: 16px; }
QLabel#userText { color: #FFFFFF; font-size: 14.5px; }

QLabel#avatar {
    background: #EFE7DA; color: #8A6D3B; border-radius: 15px;
    font-size: 15px; min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px;
}
QLabel#botName { color: #8A857C; font-size: 12.5px; font-weight: 600; }
QLabel#answer { color: #2C2A26; font-size: 15px; }
QLabel#answerError { color: #B4231F; font-size: 14px; }

QPushButton#traceHeader {
    border: none; background: transparent; color: #A29C90;
    font-size: 12.5px; text-align: left; padding: 0;
}
QPushButton#traceHeader:hover { color: #6F8F8B; }
QFrame#traceBody { border-left: 2px solid #E4DFD4; }
QLabel#traceLine { color: #A29C90; font-size: 12.5px; }

QWidget#inputBar { background: transparent; }
QFrame#composer {
    background: #FFFFFF; border: 1px solid #E4DFD4; border-radius: 20px;
}
QFrame#composer[focused="true"] { border: 1px solid #2A6F6B; }
QTextEdit#input {
    background: transparent; border: none; color: #23211E; font-size: 14.5px;
    padding: 0; selection-background-color: #BfDAD6;
}
QPushButton#send {
    background: #2A6F6B; color: #FFFFFF; border: none; border-radius: 18px;
    font-size: 17px; font-weight: 700;
    min-width: 36px; max-width: 36px; min-height: 36px; max-height: 36px;
}
QPushButton#send:hover { background: #235B57; }
QPushButton#send:disabled { background: #C2D2CF; }
QLabel#hint { color: #B7B1A4; font-size: 11.5px; }
"""


class ChatInput(QTextEdit):
    """多行输入框：Enter 发送，Shift+Enter 换行，高度随内容自适应。"""

    send_requested = Signal()

    MIN_HEIGHT = 36
    MAX_HEIGHT = 168

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedHeight(self.MIN_HEIGHT)
        self.textChanged.connect(self._adjust_height)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (
            event.modifiers() & Qt.ShiftModifier
        ):
            # 只读（请求处理中）时不响应 Enter 发送，避免误触
            if not self.isReadOnly():
                event.accept()
                self.send_requested.emit()
            return
        super().keyPressEvent(event)

    def _adjust_height(self) -> None:
        doc = self.document()
        doc.setTextWidth(self.viewport().width())
        height = int(doc.size().height()) + 8
        height = max(self.MIN_HEIGHT, min(height, self.MAX_HEIGHT))
        if height != self.height():
            self.setFixedHeight(height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._adjust_height()


class TraceSection(QWidget):
    """可折叠的「思考与检索」轨迹：运行时展开+动效，完成后自动收起。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.header = QPushButton("思考中", self)
        self.header.setObjectName("traceHeader")
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.clicked.connect(self._toggle)
        layout.addWidget(self.header, alignment=Qt.AlignLeft)

        self.body = QFrame(self)
        self.body.setObjectName("traceBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(10, 2, 0, 2)
        self.body_layout.setSpacing(4)
        layout.addWidget(self.body)

        self._steps = 0
        self._running = False
        self._expanded = True
        self._base = "思考中"
        self._dots = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.hide()  # 没有任何活动时整段不显示

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._refresh()

    def _tick(self) -> None:
        self._dots = (self._dots + 1) % 4
        self._refresh()

    def set_running(self, text: str) -> None:
        self.show()
        self._running = True
        self._expanded = True
        self._base = text
        if not self._timer.isActive():
            self._timer.start(450)
        self._refresh()

    def add_trace(self, text: str) -> None:
        self.show()
        label = QLabel(text, self.body)
        label.setObjectName("traceLine")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.body_layout.addWidget(label)
        self._steps += 1
        self._refresh()

    def mark_done(self) -> None:
        self._running = False
        self._timer.stop()
        if self._steps == 0:
            self.hide()
            return
        self._expanded = False
        self._refresh()

    def _refresh(self) -> None:
        arrow = "▾" if self._expanded else "▸"
        if self._running:
            text = f"{self._base}{'·' * self._dots}"
        else:
            text = f"已完成 · {self._steps} 步检索/操作"
        self.header.setText(f"{arrow}  {text}")
        self.body.setVisible(self._expanded)


class AssistantMessage(QWidget):
    """助手消息：头像 + 角色名 + 折叠轨迹 + Markdown 正文，占满内容列宽。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        avatar = QLabel("✎", self)
        avatar.setObjectName("avatar")
        avatar.setAlignment(Qt.AlignCenter)
        row.addWidget(avatar, 0, Qt.AlignTop)

        content = QWidget(self)
        col = QVBoxLayout(content)
        col.setContentsMargins(0, 2, 0, 0)
        col.setSpacing(6)

        name = QLabel("笔记助手", content)
        name.setObjectName("botName")
        col.addWidget(name)

        self.trace = TraceSection(content)
        col.addWidget(self.trace)

        self.answer = QLabel(content)
        self.answer.setObjectName("answer")
        self.answer.setWordWrap(True)
        self.answer.setTextFormat(Qt.MarkdownText)
        self.answer.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.answer.setOpenExternalLinks(True)
        self.answer.hide()
        col.addWidget(self.answer)

        row.addWidget(content, 1)

    def set_status(self, text: str) -> None:
        self.trace.set_running(text)

    def add_trace(self, text: str) -> None:
        self.trace.add_trace(text)

    def set_answer(self, text: str) -> None:
        self.trace.mark_done()
        self.answer.setTextFormat(Qt.MarkdownText)
        self.answer.setText(text)
        self.answer.show()

    def set_error(self, text: str) -> None:
        self.trace.mark_done()
        self.answer.setObjectName("answerError")
        self.answer.setTextFormat(Qt.PlainText)
        self.answer.setText(f"出错了：{text}")
        self.answer.style().unpolish(self.answer)
        self.answer.style().polish(self.answer)
        self.answer.show()

    def ensure_done(self) -> None:
        """确保活动轨迹停止（即便既未收到答案也未收到错误的异常退出场景）。幂等。"""
        self.trace.mark_done()


class ChatWindow(QWidget):
    def __init__(
        self,
        agent: AgentLoop,
        reporter: GuiReporter,
        notes_dir: str,
        config: AppConfig,
        config_path: str,
        rebuild_agent: Callable[[AppConfig], tuple[AgentLoop, str]],
    ):
        super().__init__()
        self.agent = agent
        self.reporter = reporter
        self.config = config
        self.config_path = config_path
        self.rebuild_agent = rebuild_agent
        self._worker: AgentWorker | None = None
        self._current_bubble: AssistantMessage | None = None

        self.setObjectName("root")
        self.setWindowTitle("Easy Note · 个人笔记助手")
        self.resize(960, 720)
        self.setMinimumSize(560, 480)
        self.setStyleSheet(STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header(notes_dir))
        root.addWidget(self._build_chat_area(), 1)
        root.addWidget(self._build_input_bar())

        self.reporter.event.connect(self._on_event)
        self._add_welcome()
        # 首跑/空配置时自动弹出设置，引导用户填写 API（打包版首次启动常见）
        QTimer.singleShot(0, self._maybe_first_run_setup)

    def closeEvent(self, event) -> None:
        # 关窗时若仍有后台请求在跑：请求中止并短暂等待，避免销毁运行中的 QThread 导致崩溃。
        # 应用为单窗口，关闭即退出进程；超时未结束的线程随进程结束被 OS 回收。
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_stop()
            self._worker.wait(2000)
        super().closeEvent(event)

    # ---- 界面构建 ----

    def _build_header(self, notes_dir: str) -> QWidget:
        header = QWidget()
        header.setObjectName("header")
        lay = QHBoxLayout(header)
        lay.setContentsMargins(20, 12, 20, 12)
        lay.setSpacing(12)

        logo = QLabel("✎")
        logo.setObjectName("logo")
        logo.setAlignment(Qt.AlignCenter)
        lay.addWidget(logo)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)
        title = QLabel("个人笔记助手")
        title.setObjectName("title")
        self.subtitle = QLabel(f"笔记目录：{notes_dir}")
        self.subtitle.setObjectName("subtitle")
        text_col.addWidget(title)
        text_col.addWidget(self.subtitle)
        lay.addLayout(text_col)
        lay.addStretch(1)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("settingsBtn")
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.setToolTip("设置")
        self.settings_btn.clicked.connect(self._open_settings)
        lay.addWidget(self.settings_btn, 0, Qt.AlignVCenter)
        return header

    def _build_chat_area(self) -> QScrollArea:
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        container.setObjectName("chat")
        outer = QHBoxLayout(container)
        outer.setContentsMargins(28, 22, 28, 22)
        outer.setSpacing(0)

        self.column = QWidget()
        self.column.setMaximumWidth(COLUMN_MAX_WIDTH)
        self.col_layout = QVBoxLayout(self.column)
        self.col_layout.setContentsMargins(0, 0, 0, 0)
        self.col_layout.setSpacing(20)
        self.col_layout.addStretch(1)

        outer.addStretch(1)
        outer.addWidget(self.column, 8)
        outer.addStretch(1)

        self.scroll.setWidget(container)
        return self.scroll

    def _build_input_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("inputBar")
        outer = QVBoxLayout(bar)
        outer.setContentsMargins(28, 6, 28, 14)
        outer.setSpacing(5)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        self.composer = QFrame()
        self.composer.setObjectName("composer")
        self.composer.setMaximumWidth(COLUMN_MAX_WIDTH)
        cbox = QHBoxLayout(self.composer)
        cbox.setContentsMargins(16, 10, 10, 10)
        cbox.setSpacing(10)

        self.input = ChatInput()
        self.input.setObjectName("input")
        self.input.setPlaceholderText("记一条笔记，或提问回顾历史…")
        self.input.send_requested.connect(self._on_send)
        self.input.installEventFilter(self)

        self.send_btn = QPushButton("↑")
        self.send_btn.setObjectName("send")
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setToolTip("发送")
        self.send_btn.clicked.connect(self._on_send_button)

        cbox.addWidget(self.input, 1)
        cbox.addWidget(self.send_btn, 0, Qt.AlignBottom)

        row.addStretch(1)
        row.addWidget(self.composer, 8)
        row.addStretch(1)
        outer.addLayout(row)

        hint = QLabel("Enter 发送 · Shift+Enter 换行")
        hint.setObjectName("hint")
        hint.setAlignment(Qt.AlignCenter)
        outer.addWidget(hint)
        return bar

    def eventFilter(self, obj, event):
        # 输入框聚焦时让 composer 边框高亮
        if obj is self.input and event.type() in (event.Type.FocusIn, event.Type.FocusOut):
            self.composer.setProperty("focused", event.type() == event.Type.FocusIn)
            self.composer.style().unpolish(self.composer)
            self.composer.style().polish(self.composer)
        return super().eventFilter(obj, event)

    # ---- 设置 ----

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.config, self)
        if dlg.exec() != SettingsDialog.Accepted:
            return
        values = dlg.values()
        save_settings(self.config_path, **values)
        # 重新加载（解析 ${ENV_VAR} 与绝对路径）并据此重建 Agent
        self.config = load_config(self.config_path)
        self.agent, notes_dir = self.rebuild_agent(self.config)
        self.subtitle.setText(f"笔记目录：{notes_dir}")

    def _maybe_first_run_setup(self) -> None:
        """空配置（打包版首跑 / 未设环境变量）时自动打开设置对话框。"""
        if not self.config.llm.api_url or not self.config.llm.api_key:
            self._open_settings()

    # ---- 消息渲染 ----

    def _append_to_column(self, widget: QWidget) -> None:
        self.col_layout.insertWidget(self.col_layout.count() - 1, widget)
        self._scroll_to_bottom()

    def _add_user_message(self, text: str) -> None:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        bubble = QFrame()
        bubble.setObjectName("userBubble")
        bubble.setMaximumWidth(USER_BUBBLE_MAX_WIDTH)
        bubble.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        lay = QVBoxLayout(bubble)
        lay.setContentsMargins(16, 11, 16, 11)
        label = QLabel(text)
        label.setObjectName("userText")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(label)

        h.addStretch(1)
        h.addWidget(bubble)
        self._append_to_column(row)

    def _add_welcome(self) -> None:
        msg = AssistantMessage()
        msg.set_answer(
            "你好，我是你的笔记助手 👋\n\n"
            "- **记笔记**：直接输入想记录的内容，我会整理标题、要点和标签后保存。\n"
            "- **查笔记**：提问回顾，我会检索历史笔记并标注来源作答。"
        )
        self._append_to_column(msg)

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()
        ))

    # ---- 交互 ----

    def _on_send_button(self) -> None:
        """发送按钮在闲时为「发送」、忙时为「停止」，据此分流。"""
        if self._worker is not None:
            self._stop_running()
        else:
            self._on_send()

    def _stop_running(self) -> None:
        if self._worker is None:
            return
        self._worker.request_stop()
        self.send_btn.setEnabled(False)
        self.send_btn.setText("…")

    def _on_send(self) -> None:
        if self._worker is not None:
            return
        text = self.input.toPlainText().strip()
        if not text:
            return

        self.input.clear()
        self._set_busy(True)
        self._add_user_message(text)

        self._current_bubble = AssistantMessage()
        self._current_bubble.set_status("思考中")
        self._append_to_column(self._current_bubble)

        self._worker = AgentWorker(self.agent, text)
        self._worker.finished_ok.connect(self._on_answer)
        self._worker.failed.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_done)
        self._worker.finished.connect(self._worker.deleteLater)  # 回收 QThread C++ 对象
        self._worker.start()

    def _on_event(self, kind: str, text: str) -> None:
        bubble = self._current_bubble
        if bubble is None:
            return
        if kind == "thinking":
            bubble.set_status("思考中")
        elif kind in ("tool", "plan"):
            bubble.set_status("处理中")
            bubble.add_trace(text)
        self._scroll_to_bottom()

    def _on_answer(self, answer: str) -> None:
        if self._current_bubble is not None:
            self._current_bubble.set_answer(answer)
        self._scroll_to_bottom()

    def _on_error(self, message: str) -> None:
        if self._current_bubble is not None:
            self._current_bubble.set_error(message)
        self._scroll_to_bottom()

    def _on_worker_done(self) -> None:
        if self._current_bubble is not None:
            # 兜底：确保轨迹停止（异常退出时可能既无答案也无错误）
            self._current_bubble.ensure_done()
        self._worker = None
        self._current_bubble = None
        self._set_busy(False)
        self.input.setFocus()

    def _set_busy(self, busy: bool) -> None:
        self.input.setReadOnly(busy)
        # 运行中禁用设置：避免中途 rebuild_agent 换掉 notes_dir，导致在途 write_note 写入旧目录
        self.settings_btn.setEnabled(not busy)
        # 运行中发送按钮变「停止」；闲时恢复「发送」
        if busy:
            self.send_btn.setEnabled(True)
            self.send_btn.setText("■")
            self.send_btn.setToolTip("停止生成")
        else:
            self.send_btn.setEnabled(True)
            self.send_btn.setText("↑")
            self.send_btn.setToolTip("发送")
