from pathlib import Path

from src.tools.base import BaseTool, ToolParameter

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50MB safety limit
MAX_OUTPUT_LINES = 500  # max lines returned per read, internal safety valve


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "读取指定文件的全部或部分内容。支持通过 start_line 和 end_line 指定行范围。单次最多返回 500 行，超过自动截断并提示继续读取。"
    parameters = [
        ToolParameter("file_path", "string", "文件的绝对或相对路径"),
        ToolParameter("start_line", "integer", "起始行号（从1开始），可选，不指定则从第一行开始", required=False),
        ToolParameter("end_line", "integer", "结束行号（含），可选，不指定则读取到文件末尾", required=False),
    ]

    def execute(self, file_path: str, start_line: int = None, end_line: int = None) -> str:
        try:
            path = self.validate_path(file_path)
        except ValueError as e:
            return f"Error: {e}"
        if not path.exists():
            return f"Error: File not found: {file_path}"
        if not path.is_file():
            return f"Error: Not a file: {file_path}"

        file_size = path.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            return (
                f"Error: File is too large ({self._format_size(file_size)}, limit is "
                f"{self._format_size(MAX_FILE_SIZE_BYTES)}). "
                f"Try using search_files to find relevant content instead."
            )
        if file_size == 0:
            return f"=== {file_path} (empty file) ===\n"

        try:
            with open(path, encoding="utf-8") as f:
                selected, total_lines = self._read_range(f, start_line, end_line)
        except _ReadRangeError as e:
            return f"Error: {e}"
        except UnicodeDecodeError:
            return (
                f"Error: Cannot read file as UTF-8 text: {file_path}\n"
                f"Hint: This may be a binary file. Use search_files to check if it contains relevant content."
            )
        except PermissionError:
            return f"Error: Permission denied: {file_path}"

        start = max((start_line or 1) - 1, 0)
        display_start = start + 1
        display_end = display_start + len(selected) - 1
        remaining = total_lines - display_end
        exhausted = (display_end >= total_lines)

        if exhausted:
            header = (
                f"=== {file_path} (lines {display_start}-{display_end}, {total_lines} total) "
                f"[FULL FILE] ===\n"
            )
        else:
            next_start = display_end + 1
            header = (
                f"=== {file_path} (lines {display_start}-{display_end} of {total_lines} total) "
                f"[TRUNCATED: {remaining} more lines after line {display_end}] ===\n"
                f"[HINT: read_file(file_path=\"{file_path}\", start_line={next_start}) to continue]\n"
            )

        return header + "".join(selected)

    def _read_range(self, f, start_line: int | None, end_line: int | None) -> tuple[list[str], int]:
        """Stream through the file and collect only the requested range of lines.

        Returns (selected_lines, total_lines). Caps at MAX_OUTPUT_LINES lines.
        """
        start = max((start_line or 1) - 1, 0)
        end = end_line  # None means read to end

        selected: list[str] = []
        effective_end = float("inf") if end is None else end

        for i, line in enumerate(f, 1):  # 1-based line numbering
            if i <= start:
                continue
            if i > effective_end:
                break
            if len(selected) < MAX_OUTPUT_LINES:
                selected.append(line)

        # Count remaining lines to determine total_lines
        total_lines = i
        for _ in f:
            total_lines += 1

        # Post-conditions: these are checked after streaming so we know total_lines
        if start >= total_lines:
            raise _ReadRangeError(f"start_line {start_line} exceeds total lines ({total_lines})")
        if start >= (end or total_lines):
            raise _ReadRangeError("start_line must be less than end_line")

        return selected, total_lines

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        else:
            return f"{size / (1024 * 1024):.1f}MB"


class _ReadRangeError(ValueError):
    """Internal sentinel for range validation errors during streaming."""