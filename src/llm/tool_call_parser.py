import json
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    name: str
    params: dict


class ToolCallParser:
    # 匹配闭合的 <tool_call>...</tool_call>
    _CLOSED_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
    # 兜底：模型撞 max_tokens 导致 </tool_call> 缺失时，取最后一个 <tool_call> 到文本末尾
    _UNCLOSED_RE = re.compile(r"<tool_call>\s*(.+)$", re.DOTALL)

    def parse(self, text: str) -> list[ToolCall]:
        if not text:
            return []
        results: list[ToolCall] = []
        matches = self._CLOSED_RE.findall(text)

        # 截断兜底：没有闭合标签但出现了 <tool_call>，尝试从未闭合处恢复
        if not matches and "<tool_call>" in text:
            matches = self._UNCLOSED_RE.findall(text)

        for m in matches:
            cleaned = self._strip_fences(m).strip()
            if not cleaned:
                continue
            try:
                data = json.loads(cleaned)
                results.append(ToolCall(
                    name=data["name"],
                    params=data.get("params", {}),
                ))
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                # 不再静默丢弃：记日志便于排查"agent 为什么没动作"
                logger.debug("dropped malformed tool_call: %r (%s)", cleaned[:200], e)
                continue
        return results

    @staticmethod
    def _strip_fences(text: str) -> str:
        """去掉模型常加的 ```json ... ``` 围栏，避免 json.loads 失败。"""
        s = text.strip()
        if s.startswith("```"):
            # 去掉首行（``` 或 ```json）
            s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
        return s.strip()
