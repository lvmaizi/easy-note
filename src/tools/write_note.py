"""write_note 工具：把整理后的笔记追加写入按日期命名的 markdown 日记文件。

存储策略：每天一个 `YYYY-MM-DD.md`，新笔记以二级标题条目形式追加到当天文件末尾。
仿照 UpdatePlanTool 的"构造时注入"模式，注入的是笔记目录路径，并复用 BaseTool.validate_path 做沙箱校验。
"""

import os
from datetime import datetime
from pathlib import Path

from src.tools.base import BaseTool, ToolParameter


class WriteNoteTool(BaseTool):
    name = "write_note"
    description = (
        "把整理后的笔记追加写入按日期命名的 markdown 文件（每天一个 YYYY-MM-DD.md）。"
        "当用户在陈述、记事、倾诉或明确表达『记一下/帮我记/写笔记』等意图时调用。"
        "调用前请先把用户原话结构化整理：提炼标题、把内容整理成清晰要点、生成相关标签。"
    )
    parameters = [
        ToolParameter("title", "string", "为这条笔记提炼的简短标题"),
        ToolParameter(
            "content",
            "string",
            "整理后的正文，可使用 markdown 列表/要点等格式组织内容",
        ),
        ToolParameter(
            "tags",
            "array",
            '标签列表，如 ["编程", "读书"]，用于后续归类检索，可选',
            required=False,
        ),
    ]

    def __init__(self, notes_dir: str):
        super().__init__([notes_dir])  # allowed_dirs 设为笔记目录，复用沙箱校验
        self.notes_dir = notes_dir

    def execute(self, title: str, content: str, tags=None) -> str:
        if not isinstance(title, str) or not title.strip():
            return "Error: title 必须是非空字符串"
        if not isinstance(content, str) or not content.strip():
            return "Error: content 必须是非空字符串"

        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M")
        target = Path(self.notes_dir) / f"{date_str}.md"

        try:
            self.validate_path(str(target))
        except ValueError as e:
            return f"Error: {e}"

        try:
            Path(self.notes_dir).mkdir(parents=True, exist_ok=True)
            # 打开后用 f.tell()==0 判定是否需要写日期大标题：消除 exists() 与写入之间的 TOCTOU
            # （并发写入或编辑器保存可能导致同一文件出现两个大标题）。
            # flush+fsync 确保笔记落盘，避免崩溃丢失缓冲区内容。
            with open(target, "a", encoding="utf-8") as f:
                is_new = f.tell() == 0
                entry = self._format_entry(date_str, time_str, title.strip(), content.strip(), tags, is_new)
                f.write(entry)
                f.flush()
                os.fsync(f.fileno())
        except OSError as e:
            return f"Error: 写入失败: {e}"

        try:
            shown = target.relative_to(Path(self.notes_dir).parent)
        except ValueError:
            shown = target
        return f"已保存到 {shown}（标题：{title.strip()}）"

    @staticmethod
    def _format_entry(date_str, time_str, title, content, tags, is_new) -> str:
        parts = []
        if is_new:
            parts.append(f"# {date_str}\n\n")
        parts.append(f"## {time_str} {title}\n\n")
        parts.append(f"{content}\n\n")
        if tags:
            tag_list = tags if isinstance(tags, list) else [tags]
            tag_str = " ".join(f"#{str(t).strip()}" for t in tag_list if str(t).strip())
            if tag_str:
                parts.append(f"Tags: {tag_str}\n\n")
        parts.append("---\n\n")
        return "".join(parts)
