import logging
import re
from pathlib import Path

from src.tools.base import BaseTool, ToolParameter

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {".py", ".md", ".txt", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini", ".log", ".csv", ".xml", ".html", ".css", ".js", ".ts", ".sh", ".bat", ".rst"}

# 内容搜索时单文件大小上限：超过则只做文件名匹配，不读取内容，防大文件挂死 agent 线程
MAX_CONTENT_FILE_SIZE = 5 * 1024 * 1024  # 5MB



class SearchFilesTool(BaseTool):
    name = "search_files"
    description = (
        "在本地目录中搜索文件，同时匹配文件名和文件内容。"
        "最多返回 20 个文件，每个文件最多显示 20 行匹配内容。"
        "如果结果被截断，尝试使用更精确的搜索模式重新搜索。"
    )
    parameters = [
        ToolParameter("pattern", "string", "搜索模式（字面子串或正则表达式）。普通子串大小写不敏感（如 '三国'），可用 | 匹配多个候选模式（如 '三国|水浒|西游'），也支持完整正则语法（如 'import\\s+os'）。多个候选模式用 | 分隔。"),
        ToolParameter("search_dir", "string", "搜索的目标目录路径，不指定则使用默认目录", required=False),
        ToolParameter("search_content", "boolean", "是否搜索文件内容，默认 true", required=False),
    ]

    def execute(self, pattern: str, search_dir: str = None, search_content: bool = True) -> str:
        if search_dir:
            try:
                resolved = self.validate_path(search_dir)
                target_dirs = [str(resolved)]
            except ValueError as e:
                return f"Error: {e}"
        else:
            target_dirs = self.allowed_dirs

        # Build a case-insensitive regex from the pattern
        matcher = self._build_matcher(pattern)

        results: list[dict] = []

        for d in target_dirs:
            base = Path(d)
            if not base.exists():
                continue
            for file_path in base.rglob("*"):
                # 沙箱二次校验：rglob 会跟随符号链接/junction，须逐个确认解析后仍在允许目录内，
                # 否则外部文件内容会被读出返给 LLM（-> 云端）
                if file_path.is_symlink():
                    continue
                if not file_path.is_file():
                    continue
                try:
                    self.validate_path(str(file_path))
                except ValueError:
                    continue

                ext = file_path.suffix.lower()

                name_match = matcher.search(file_path.name)

                content_matches: list[str] = []
                if search_content and ext in TEXT_EXTENSIONS:
                    try:
                        file_size = file_path.stat().st_size
                    except OSError:
                        file_size = 0
                    # 大文件只做文件名匹配，避免读取多 MB 日志挂死 agent 线程
                    if 0 < file_size <= MAX_CONTENT_FILE_SIZE:
                        try:
                            with open(file_path, encoding="utf-8") as f:
                                for i, line in enumerate(f, 1):
                                    m = matcher.search(line)
                                    if m:
                                        content_matches.append(f"  L{i}: {line.strip()[:200]}")
                                        if len(content_matches) >= 20:
                                            break
                        except (UnicodeDecodeError, PermissionError):
                            pass

                if name_match or content_matches:
                    results.append({
                        "path": str(file_path),
                        "name_match": bool(name_match),
                        "content_matches": content_matches,
                    })

        if not results:
            return f"未找到匹配 '{pattern}' 的文件。尝试用更简短的模式或 list_directory 浏览目录结构。"

        results.sort(key=lambda r: (not r["name_match"], -len(r["content_matches"])))

        total = len(results)
        lines = []
        for r in results[:20]:
            try:
                size_str = self._format_size(Path(r["path"]).stat().st_size)
            except OSError:
                size_str = "?"
            match_type = "文件名匹配" if r["name_match"] else "内容匹配"
            lines.append(f"{r['path']} [{size_str}] ({match_type})")
            for cm in r["content_matches"]:
                lines.append(cm)
            lines.append("")

        header = f"找到 {total} 个相关文件"
        if total > 20:
            header += "，显示前 20 个"
        header += "：\n"
        return header + "\n".join(lines)

    def _build_matcher(self, pattern: str) -> re.Pattern:
        """Build a case-insensitive regex from the user's pattern.

        Strategy:
        1. If the pattern contains regex meta-chars beyond simple text, use it as-is (regex mode).
        2. Otherwise, escape it and use as a literal substring match (plain mode).
        3. In both cases the result is a single regex, so callers just use .search().
        """
        # Characters that suggest the user is writing a regex, not a plain literal pattern
        regex_hints = {'\\', '|', '^', '$', '.', '*', '+', '?', '[', ']', '(', ')', '{', '}'}
        has_regex_hints = any(c in pattern for c in regex_hints)

        if has_regex_hints:
            try:
                return re.compile(pattern, re.IGNORECASE)
            except re.error:
                # Regex compile failed - fall through to auto-split mode
                pass

        # Plain literal mode: escape regex metachars and use as literal substring
        return re.compile(re.escape(pattern), re.IGNORECASE)

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        else:
            return f"{size / (1024 * 1024):.1f}MB"
