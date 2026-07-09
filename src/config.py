"""配置数据结构定义与 YAML 加载。

- dataclass：LLMConfig / CompactionConfig / AppConfig
- load_config：读取 config.yaml，解析 ${ENV_VAR}，把 search_dirs 解析为绝对路径
"""

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def user_data_dir() -> Path:
    """跨平台可写用户数据目录。

    Windows %APPDATA%/EasyNote；macOS ~/Library/Application Support/EasyNote；
    Linux 遵循 XDG：$XDG_DATA_HOME/EasyNote，未设则 ~/.local/share/EasyNote。

    打包后用户配置与笔记默认落在此处，避免写入 exe 同级（Program Files 等受保护目录）失败。
    """
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "EasyNote"
    if sys.platform.startswith("linux"):
        xdg = os.environ.get("XDG_DATA_HOME")
        if xdg:
            return Path(xdg) / "EasyNote"
        return Path.home() / ".local" / "share" / "EasyNote"
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home()
    return root / "EasyNote"


@dataclass
class LLMConfig:
    # 默认用环境变量占位：使用方首次运行前自行设置（环境变量或在设置对话框填入），
    # 不内置任何真实凭据，避免随发行包泄露。
    api_url: str = "${OPENAI_API_URL}"
    api_key: str = "${OPENAI_API_KEY}"
    model: str = "${OPENAI_MODEL}"
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class CompactionConfig:
    """上下文压缩三档分层配置。所有阈值都是占 (context_budget - reserved_output) 的比例。"""

    context_budget_tokens: int = 100_000
    reserved_output_tokens: int = 4096
    snip_threshold: float = 0.60
    micro_threshold: float = 0.75
    auto_threshold: float = 0.85
    critical_threshold: float = 0.92
    single_msg_max_tokens: int = 4000   # snip: 单条 tool_result 上限
    micro_summarize_count: int = 3      # micro: 每次摘要最旧 tool_result 条数
    keep_recent_turns: int = 3          # auto: 保留最近 N 条 assistant 消息及其后续工具结果


@dataclass
class AppConfig:
    search_dirs: list[str]
    llm: LLMConfig
    notes_dir: str = "./notes"
    compaction: CompactionConfig = field(default_factory=CompactionConfig)


def _resolve_env_vars(value: str) -> str:
    """Replace ${ENV_VAR} patterns with environment variable values."""
    if not isinstance(value, str):
        return value
    pattern = re.compile(r"\$\{(\w+)\}")
    return pattern.sub(lambda m: os.environ.get(m.group(1), ""), value)


def _yaml_single_quote(value: str) -> str:
    """以单引号包裹标量：YAML 单引号串里反斜杠是字面量（适配 Windows 路径），单引号需翻倍。"""
    return "'" + str(value).replace("'", "''") + "'"


def _default_yaml(api_url: str, api_key: str, model: str, notes_dir: str) -> str:
    """生成一份完整 config.yaml（含 compaction 默认段、空 search_dirs），供首次保存时落盘。"""
    return (
        "# LLM API 配置\n"
        "llm:\n"
        f"  api_url: {_yaml_single_quote(api_url)}\n"
        f"  api_key: {_yaml_single_quote(api_key)}\n"
        f"  model: {_yaml_single_quote(model)}\n"
        "  temperature: 0.7\n"
        "  max_tokens: 4096\n"
        "\n"
        "# 本地检索目录（查询笔记时会自动并入 notes_dir）\n"
        "search_dirs: []\n"
        "\n"
        "# 笔记保存目录（write_note 写入、查询时自动检索）\n"
        f"notes_dir: {_yaml_single_quote(notes_dir)}\n"
        "\n"
        "# 上下文压缩（snip / micro / auto 三档分层）\n"
        "# 阈值 = 占 (context_budget_tokens - reserved_output_tokens) 的比例\n"
        "# 触发顺序：每轮末尾按 auto > micro > snip 倒序判定，命中即停\n"
        "compaction:\n"
        "  context_budget_tokens: 100000\n"
        "  reserved_output_tokens: 4096\n"
        "  snip_threshold: 0.60         # 纯规则截断单条超大 tool_result\n"
        "  micro_threshold: 0.75        # LLM 摘要最旧的几条 tool_result\n"
        "  auto_threshold: 0.85         # LLM 全局摘要替换历史\n"
        "  critical_threshold: 0.92     # 兜底：注入\"请直接给出最终回答\"\n"
        "  single_msg_max_tokens: 4000  # snip: 单条 tool_result token 上限\n"
        "  micro_summarize_count: 3     # micro: 每次摘要最旧的 N 条\n"
        "  keep_recent_turns: 3         # auto: 保留最近 N 条 assistant 及其后续工具结果\n"
    )


def _default_config() -> AppConfig:
    """无配置文件时的内置默认配置：dataclass 默认值 + 用户目录下的 notes_dir。

    打包后首次运行不依赖任何外部文件即可启动；用户在设置对话框保存后才在用户目录落盘。
    """
    llm = LLMConfig()
    # 与读 yaml 一致：解析 ${ENV_VAR} 占位（环境变量未设置时为空字符串，
    # 引导使用方在设置对话框填入自己的凭据）
    llm.api_url = _resolve_env_vars(llm.api_url)
    llm.api_key = _resolve_env_vars(llm.api_key)
    llm.model = _resolve_env_vars(llm.model)
    return AppConfig(
        search_dirs=[],
        llm=llm,
        notes_dir=str(user_data_dir() / "notes"),
        compaction=CompactionConfig(),
    )


def save_settings(
    path: str,
    *,
    api_url: str,
    api_key: str,
    model: str,
    notes_dir: str,
) -> None:
    """就地更新 config.yaml 中的必填项，保留原有注释与其余字段。

    - 文件已存在：采用按行替换，仅改写 llm 段下的 api_url/api_key/model 以及顶层 notes_dir，
      其它行原样保留。
    - 文件不存在（首次保存）：生成一份完整 yaml（含 compaction 默认段）后落盘，并按需创建目录。
    """
    target = Path(path)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            _default_yaml(api_url, api_key, model, notes_dir), encoding="utf-8"
        )
        return

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    llm_updates = {"api_url": api_url, "api_key": api_key, "model": model}
    section: str | None = None
    out: list[str] = []
    for line in lines:
        # 顶层（无缩进）的 `key:` 切换当前所在段
        top = re.match(r"^(\w+):", line)
        if top:
            section = top.group(1)

        m = re.match(r"^(\s*)(\w+):", line)
        if m:
            indent, key = m.group(1), m.group(2)
            if indent and section == "llm" and key in llm_updates:
                out.append(f"{indent}{key}: {_yaml_single_quote(llm_updates[key])}\n")
                continue
            if not indent and key == "notes_dir":
                out.append(f"notes_dir: {_yaml_single_quote(notes_dir)}\n")
                continue
        out.append(line)

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(out)


def load_config(path: str = "config.yaml") -> AppConfig:
    """读取 config.yaml；文件不存在时回退到内置默认值（打包后首次运行无需任何外部文件）。"""
    if not Path(path).exists():
        return _default_config()

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    llm_data = {k: _resolve_env_vars(v) for k, v in data["llm"].items()}
    llm_config = LLMConfig(**llm_data)

    project_root = Path(path).resolve().parent
    raw_dirs = data.get("search_dirs", [])
    search_dirs = [str(project_root.joinpath(d).resolve()) for d in raw_dirs]

    raw_notes_dir = data.get("notes_dir", "./notes")
    notes_dir = str(project_root.joinpath(raw_notes_dir).resolve())

    compaction_data = data.get("compaction", {}) or {}
    compaction = CompactionConfig(**compaction_data)

    return AppConfig(
        search_dirs=search_dirs,
        llm=llm_config,
        notes_dir=notes_dir,
        compaction=compaction,
    )
