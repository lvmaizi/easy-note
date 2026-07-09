"""上下文压缩三档分层（参考 Claude Code 的 snip / micro / auto）。

- snip_compact：纯规则截断单条超大 tool_result（不调 LLM）
- micro_compact：对最旧的 N 条 tool_result 逐条调 LLM 写一句话摘要
- auto_compact：调一次 LLM 生成结构化全局摘要，替换历史片段

所有函数都返回"省下的 token 数"，便于日志/通知。
"""

from src.conversation.context import ConversationContext
from src.conversation.tokens import count_tokens
from src.llm.client import LLMClient


_MICRO_PROMPT = """请把下面这段工具调用结果浓缩成一段不超过 80 字的中文摘要，保留：
1. 该次调用的关键发现（找到的文件路径、函数名、行号、关键文本）
2. 任何错误或异常信息

其他冗长细节都可以丢弃。**直接输出摘要文字本身**，不要 XML 包装、不要 markdown、不要解释。

工具结果原文：
{content}
"""


_AUTO_SYSTEM = """你是一个对话历史摘要器。你的唯一任务是把传入的多轮对话历史浓缩为指定 XML schema 的简短摘要。
严格按 schema 输出，不要任何前后缀文字、不要 markdown 代码块包裹。"""


_AUTO_USER_TEMPLATE = """请将以下对话历史压缩为简短摘要，严格按下面的 XML schema 输出（中文，每段一两句即可）：

<global_summary>
<original_question>用户最初提出的问题原文</original_question>
<key_findings>
- 已经获得的关键事实 1
- 已经获得的关键事实 2
</key_findings>
<files_read>
- 已读过的文件路径:行号范围
</files_read>
<progress>当前进展，一两句话说明已经做了什么、得到什么阶段性结论</progress>
<pending>尚未完成或下一步应当继续的工作</pending>
</global_summary>

原始用户问题：
{user_question}

需要压缩的历史对话（assistant 思考与工具结果交错）：
{history}
"""


def snip_compact(ctx: ConversationContext, single_msg_max_tokens: int) -> int:
    """档 1：扫描所有 tool_result，对单条 token 数超过 single_msg_max_tokens 的纯规则截断。

    复用 ConversationContext._summarize_tool_result 的策略表（read_file / search_files /
    list_directory / 通用 fallback）。不调 LLM。
    """
    tokens_before = ctx.total_tokens()
    for idx in ctx.find_tool_result_indices():
        if ctx._message_tokens[idx] <= single_msg_max_tokens:
            continue
        original = ctx.messages[idx]["content"]
        summary = ctx._summarize_tool_result(original)
        if len(summary) < len(original):
            ctx.update_message(idx, summary)
    return max(0, tokens_before - ctx.total_tokens())


def micro_compact(ctx: ConversationContext, llm: LLMClient, count: int) -> int:
    """档 2：取最旧的 count 条 tool_result，每条调一次 LLM 写一句话摘要替换。

    每次摘要调用是一次独立的小 chat（system + user 两条消息），不会污染主对话。
    """
    tokens_before = ctx.total_tokens()
    indices = ctx.find_oldest_tool_results(count)
    if not indices:
        return 0

    for idx in indices:
        original = ctx.messages[idx]["content"]
        # 已经被 snip 过的（compressed="true"）就不再 micro，避免重复
        if 'compressed="true"' in original or "[micro_compacted]" in original:
            continue
        try:
            summary_text = _summarize_via_llm(
                llm,
                system_prompt="你是一个工具结果摘要器，严格按用户要求只输出摘要文字。",
                user_prompt=_MICRO_PROMPT.format(content=original),
            )
        except (ConnectionError, TimeoutError, RuntimeError):
            # 摘要失败就跳过这条，下一轮 auto_compact 还会兜底
            continue
        # 保留 tool_result 包装以便 LLM 识别这是一次工具调用的产物
        tool_name = _extract_tool_name(original)
        new_content = (
            f'<tool_result name="{tool_name}" compressed="true" mode="micro">\n'
            f"[micro_compacted] {summary_text.strip()}\n"
            f"</tool_result>"
        )
        if count_tokens(new_content) < ctx._message_tokens[idx]:
            ctx.update_message(idx, new_content)

    return max(0, tokens_before - ctx.total_tokens())


def auto_compact(ctx: ConversationContext, llm: LLMClient, keep_recent_turns: int) -> int:
    """档 3：全局摘要。调一次 LLM 按固定 schema 输出，替换 messages[1:cut] 为单条摘要消息。

    cut 为最近第 keep_recent_turns 条 assistant 消息的索引，从该处起的所有消息（包括其后续 tool_result）保留原文。
    保留 messages[0]（system prompt）不动。
    """
    tokens_before = ctx.total_tokens()

    assistant_indices = [
        i for i, m in enumerate(ctx.messages) if m["role"] == "assistant"
    ]
    if len(assistant_indices) <= keep_recent_turns:
        return 0  # 历史太短，没必要压

    cut_idx = assistant_indices[-keep_recent_turns]
    if cut_idx <= 1:
        return 0

    user_question = ctx.get_user_question()
    history_chunk = ctx.messages[1:cut_idx]
    history_text = _render_history(history_chunk)

    try:
        summary_text = _summarize_via_llm(
            llm,
            system_prompt=_AUTO_SYSTEM,
            user_prompt=_AUTO_USER_TEMPLATE.format(
                user_question=user_question or "(unknown)",
                history=history_text,
            ),
        )
    except (ConnectionError, TimeoutError, RuntimeError):
        # 摘要调用失败：降级到 snip，不破坏现有 messages
        return snip_compact(ctx, single_msg_max_tokens=2000)

    summary_msg = {
        "role": "user",
        "content": (
            "<compacted_history mode=\"auto\">\n"
            f"{summary_text.strip()}\n"
            "</compacted_history>\n\n"
            "以上是之前对话的压缩摘要。请基于摘要中的事实继续工作；如需原始内容请重新调用工具读取。\n"
            f"用户最初的问题：{user_question}"
        ),
    }
    ctx.replace_range(1, cut_idx, [summary_msg])

    # 不变量：messages[0] 必须仍是 system prompt
    assert ctx.messages[0]["role"] == "system", "auto_compact 破坏了 system prompt 不变量"

    return max(0, tokens_before - ctx.total_tokens())


# ---- 内部辅助 ---------------------------------------------------------------


def _summarize_via_llm(llm: LLMClient, system_prompt: str, user_prompt: str) -> str:
    """启动一个独立的两条消息小对话调用 LLM 写摘要。不污染主 context。"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return llm.chat(messages)


def _extract_tool_name(tool_result_content: str) -> str:
    import re
    m = re.search(r'name="([^"]+)"', tool_result_content)
    return m.group(1) if m else "unknown"


def _render_history(messages: list[dict]) -> str:
    """把一段消息列表序列化为 LLM 可读的纯文本块（用于摘要 prompt 的输入）。"""
    parts = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content", "")
        # 整体上限保护：避免传给摘要器的 prompt 自己就爆掉
        if len(content) > 2000:
            content = content[:2000] + "\n...[truncated for summarization]"
        parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts)
