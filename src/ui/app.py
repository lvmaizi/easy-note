"""桌面聊天客户端入口：读配置、组装组件并启动 QApplication。

组装 config / registry / AgentLoop，reporter 用 GuiReporter，交互层用 ChatWindow。

运行：
    python -m src.ui.app
"""

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from src.agent.loop import AgentLoop
from src.config import AppConfig, load_config, user_data_dir
from src.llm.client import LLMClient
from src.plan import PlanState, render_plan_as_messages
from src.prompts import build_system_prompt
from src.tools.list_directory import ListDirectoryTool
from src.tools.read_file import ReadFileTool
from src.tools.registry import ToolRegistry
from src.tools.search_files import SearchFilesTool
from src.tools.update_plan import UpdatePlanTool
from src.tools.write_note import WriteNoteTool
from src.ui.chat_window import ChatWindow
from src.ui.reporter import GuiReporter


def config_path() -> str:
    """返回可持久写入的用户配置路径。

    - 打包后（frozen）：用户数据目录下的 config.yaml（可写，设置对话框可写回）。
    - 源码运行：仓库根目录的 config.yaml。

    首次运行无需任何外部文件：load_config 在文件缺失时回退到内置默认值，
    用户首次保存设置时 save_settings 才在此路径落盘。
    """
    if getattr(sys, "frozen", False):
        target = user_data_dir() / "config.yaml"
    else:
        target = Path(__file__).resolve().parents[2] / "config.yaml"
    return str(target)


def app_icon() -> QIcon:
    """加载自定义应用图标；找不到时返回空 QIcon（退回系统默认）。

    查找顺序：assets/icon.ico → assets/icon.png（源码与 PyInstaller 打包均适用）。
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    for name in ("icon.ico", "icon.png"):
        candidate = base / "assets" / name
        if candidate.exists():
            return QIcon(str(candidate))
    return QIcon()


def build_agent(reporter: GuiReporter, config: AppConfig):
    """组装 registry + AgentLoop，返回 (agent, notes_dir)。"""
    # 只读文件工具的可访问范围 = 检索目录 + 笔记目录
    allowed_dirs = config.search_dirs + [config.notes_dir]

    plan_state = PlanState()
    plan_state.observers.append(reporter.plan_changed)

    registry = ToolRegistry()
    registry.register(SearchFilesTool(allowed_dirs))
    registry.register(ReadFileTool(allowed_dirs))
    registry.register(ListDirectoryTool(allowed_dirs))
    registry.register(WriteNoteTool(config.notes_dir))
    registry.register(UpdatePlanTool(plan_state))

    llm = LLMClient(config.llm)
    system_prompt = build_system_prompt(registry, allowed_dirs, config.notes_dir)
    agent = AgentLoop(
        llm,
        registry,
        system_prompt,
        compaction_config=config.compaction,
        reporter=reporter,
        extra_messages_provider=lambda: render_plan_as_messages(plan_state),
        on_new_turn=lambda: plan_state.clear() if plan_state.all_completed() else None,
    )
    return agent, config.notes_dir


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(app_icon())
    reporter = GuiReporter()
    path = config_path()
    config = load_config(path)
    agent, notes_dir = build_agent(reporter, config)
    window = ChatWindow(
        agent,
        reporter,
        notes_dir,
        config,
        path,
        rebuild_agent=lambda cfg: build_agent(reporter, cfg),
    )
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
