from pathlib import Path

from src.tools.base import BaseTool, ToolParameter

TEXT_EXTENSIONS = {
    ".py", ".md", ".txt", ".yaml", ".yml", ".json", ".toml", ".cfg",
    ".ini", ".log", ".csv", ".xml", ".html", ".css", ".js", ".ts",
    ".sh", ".bat", ".rst",
}

# 递归列出时的条目上限，防大目录（node_modules / 主目录）撑爆内存与上下文
MAX_ENTRIES = 500


class ListDirectoryTool(BaseTool):
    name = "list_directory"
    description = "列出指定目录下的所有文件和子目录。用于了解项目结构，发现可读取的文件。返回文件类型、大小和路径。"
    parameters = [
        ToolParameter("directory", "string", "要列出的目录路径（相对或绝对路径）"),
        ToolParameter("recursive", "boolean", "是否递归列出子目录，默认 false", required=False),
    ]

    def execute(self, directory: str, recursive: bool = False) -> str:
        try:
            base = self.validate_path(directory)
        except ValueError as e:
            return f"Error: {e}"
        if not base.exists():
            return f"Error: Directory not found: {directory}"
        if not base.is_dir():
            return f"Error: Not a directory: {directory}"

        # 流式收集：遇符号链接跳过并二次校验沙箱（rglob 会跟随链接），到上限即停
        iterator = base.rglob("*") if recursive else base.iterdir()
        collected: list[Path] = []
        truncated = False
        for entry in iterator:
            if entry.name.startswith("."):
                continue
            if entry.is_symlink():
                continue
            try:
                self.validate_path(str(entry))
            except ValueError:
                continue
            collected.append(entry)
            if len(collected) >= MAX_ENTRIES:
                truncated = True
                break

        collected.sort(key=lambda p: (p.is_dir(), p.name.lower()))

        lines = [f"Contents of {base.absolute()}:\n"]
        file_count = 0
        dir_count = 0

        for entry in collected:
            if entry.is_dir():
                lines.append(f"  [DIR]  {entry.name}/")
                dir_count += 1
            elif entry.is_file():
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0
                size_str = self._format_size(size)
                is_text = entry.suffix.lower() in TEXT_EXTENSIONS
                type_tag = "TEXT" if is_text else "BIN "
                lines.append(f"  [{type_tag}] {entry.name} ({size_str})")
                file_count += 1

        summary = f"\n{dir_count} directories, {file_count} files"
        if truncated:
            summary += f"（仅显示前 {MAX_ENTRIES} 项，更多未列出，请缩小范围或改用 search_files）"
        return "\n".join(lines) + summary

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        else:
            return f"{size / (1024 * 1024):.1f}MB"
