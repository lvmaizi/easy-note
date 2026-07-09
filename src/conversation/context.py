import re

from src.conversation.tokens import count_tokens


class ConversationContext:
    def __init__(self, system_prompt: str):
        self.messages: list[dict] = [{"role": "system", "content": system_prompt}]
        self._message_tokens: list[int] = [count_tokens(system_prompt)]

    def add_user_message(self, content: str):
        self.messages.append({"role": "user", "content": content})
        self._message_tokens.append(count_tokens(content))

    def add_assistant_message(self, content: str):
        self.messages.append({"role": "assistant", "content": content})
        self._message_tokens.append(count_tokens(content))

    def add_tool_result(self, tool_name: str, result: str):
        content = f'<tool_result name="{tool_name}">\n{result}\n</tool_result>'
        self.messages.append({"role": "user", "content": content})
        self._message_tokens.append(count_tokens(content))

    def get_messages(self) -> list[dict]:
        return self.messages

    def total_tokens(self) -> int:
        return sum(self._message_tokens)

    def estimate_tokens(self) -> int:
        return self.total_tokens()

    def total_chars(self) -> int:
        return sum(len(msg.get("content", "")) for msg in self.messages)

    def recount_tokens(self):
        """Recompute token counts for all messages. Call after external message modification."""
        self._message_tokens = [count_tokens(msg.get("content", "")) for msg in self.messages]

    # ---- 通用编辑 API（供 compactor 使用，三档压缩共用基础设施） -------------

    def update_message(self, idx: int, content: str):
        """单条消息内容替换，自动同步 token 计数。"""
        self.messages[idx]["content"] = content
        self._message_tokens[idx] = count_tokens(content)

    def replace_range(self, start: int, end: int, new_msgs: list[dict]):
        """替换 messages[start:end] 为 new_msgs，自动维护 _message_tokens 同步。

        约束：禁止删除或覆盖 messages[0]（system prompt）。
        """
        assert start >= 1, "禁止替换 system prompt（messages[0]）"
        new_tokens = [count_tokens(m.get("content", "")) for m in new_msgs]
        self.messages[start:end] = new_msgs
        self._message_tokens[start:end] = new_tokens

    def find_tool_result_indices(self) -> list[int]:
        """返回所有 tool_result 消息的索引（按出现顺序）。"""
        return [
            i for i, msg in enumerate(self.messages)
            if msg["role"] == "user" and msg["content"].startswith("<tool_result")
        ]

    def find_oldest_tool_results(self, n: int) -> list[int]:
        """返回最旧的 n 个 tool_result 消息索引。"""
        return self.find_tool_result_indices()[:n]

    def get_user_question(self) -> str:
        """返回首条用户提问（messages[1]，紧随 system prompt 之后）。"""
        for msg in self.messages[1:]:
            if msg["role"] == "user" and not msg["content"].startswith("<tool_result"):
                return msg["content"]
        return ""

    def is_tool_result(self, idx: int) -> bool:
        msg = self.messages[idx]
        return msg["role"] == "user" and msg["content"].startswith("<tool_result")

    # ---- 旧接口（向后兼容，内部代理给 snip 策略） -----------------------------

    def compress_tool_results(self, keep_last_n: int = 3) -> int:
        """[Deprecated] 旧接口：按 keep_last_n 保留最新工具结果，其余按工具名规则截断。

        新代码请直接调用 src.conversation.compaction.snip_compact。本方法保留以避免破坏既有调用点。
        """
        tokens_before = self.total_tokens()
        tool_indices = self.find_tool_result_indices()

        if len(tool_indices) <= keep_last_n:
            return 0

        for idx in tool_indices[:-keep_last_n]:
            content = self.messages[idx]["content"]
            summary = self._summarize_tool_result(content)
            if len(summary) < len(content):
                self.update_message(idx, summary)

        return max(0, tokens_before - self.total_tokens())

    def _summarize_tool_result(self, content: str) -> str:
        """按工具名规则压缩 tool_result。snip_compact 复用此分派表。"""
        name_match = re.search(r'name="([^"]+)"', content)
        tool_name = name_match.group(1) if name_match else "unknown"

        if tool_name == "read_file":
            first_newline = content.find("\n")
            header = content[:first_newline] if first_newline > 0 else content[:200]
            return (
                f'<tool_result name="{tool_name}" compressed="true">\n'
                f"{header}\n"
                f"[Content compressed to save context space. Re-read the file if needed.]\n"
                f"</tool_result>"
            )

        if tool_name == "search_files":
            lines = content.split("\n")
            kept = [l for l in lines if not l.startswith("  L") and l.strip()]
            return (
                f'<tool_result name="{tool_name}" compressed="true">\n'
                + "\n".join(kept[:30])
                + "\n[Match details compressed]</tool_result>"
            )

        if tool_name == "list_directory":
            if len(content) > 2000:
                return content[:2000] + "\n...[truncated]\n</tool_result>"
            return content

        # Generic: keep first 500 chars
        if len(content) > 500:
            return content[:500] + "\n...[compressed]"
        return content
