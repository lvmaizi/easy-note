import logging
from typing import Callable

from src.config import CompactionConfig
from src.conversation.compaction import auto_compact, micro_compact, snip_compact
from src.conversation.context import ConversationContext
from src.llm.client import LLMClient
from src.llm.tool_call_parser import ToolCallParser
from src.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentLoop:
    # 终答自检门：模型给出无工具调用的回答时，最多逼它再检索这么多轮，防死循环。
    MAX_REFLECTIONS = 2

    # 安全阀：防模型不停调工具把 API 预算刷爆。
    # MAX_TOOL_CALLS 达到后注入"请直接作答"通知并跳过自检门；MAX_ITERATIONS 是硬上限，无论如何都停。
    MAX_TOOL_CALLS = 30
    MAX_ITERATIONS = 40

    # 出现这些措辞时，认为模型在"认输"或凭先验知识作答，需逼它继续检索。
    _GIVEUP_MARKERS = (
        "找不到", "未找到", "没有找到", "无法找到", "无法确定",
        "无法回答", "没有相关", "未能找到", "查无",
    )
    _KNOWLEDGE_MARKERS = ("据我所知", "根据我的了解", "我的知识", "众所周知", "一般来说")

    _REFLECTION_PROMPT = (
        "[System] 在给出最终答案前请自检：\n"
        "(1) 如果用户是在记录笔记，你是否已调用 write_note 把整理后的内容实际保存？"
        "不要只在回复里复述而不落盘。\n"
        "(2) 如果用户是在查询笔记，你是否已用 search_files / read_file 在笔记目录中检索，"
        "并换过至少 2~3 种关键词/同义词？回答是否基于检索到的笔记内容并标注了来源文件，"
        "而非你的先验知识？\n"
        "如果还有未完成的保存或未试过的检索路径，请继续调用工具；"
        "只有当你确实完成了保存、或已穷尽检索仍找不到时，才给出最终回复。"
    )

    _STOPPED_MESSAGE = "⏹ 已停止生成"
    _MAX_STEPS_MESSAGE = "（已达最大处理步数，已停止。请尝试缩小问题范围或换个问法。）"

    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        system_prompt: str,
        compaction_config: CompactionConfig | None = None,
        reporter=None,
        extra_messages_provider: Callable[[], list[dict]] = lambda: [],
        on_new_turn: Callable[[], None] = lambda: None,
    ):
        self.llm = llm_client
        self.registry = tool_registry
        self.parser = ToolCallParser()
        self.system_prompt = system_prompt
        self.compaction = compaction_config or CompactionConfig()
        self.context = ConversationContext(system_prompt)
        # reporter 由 GUI 注入（GuiReporter），用鸭子类型调用其同名进度方法
        self.reporter = reporter
        self.extra_messages_provider = extra_messages_provider
        self.on_new_turn = on_new_turn
        self._budget_exhausted = False
        # 协作式取消标志：由外部（AgentWorker.request_stop）置位，循环在安全点检查后退出。
        self._cancel = False

    def cancel(self) -> None:
        """请求中止当前 run。在下一次安全检查点（循环顶端 / LLM 返回后）生效。

        无法中断进行中的 HTTP 请求；最坏需等当前 LLM 调用返回（受 client 超时约束）。
        """
        self._cancel = True

    def run(self, user_input: str) -> str:
        self.on_new_turn()
        self.reporter.start(user_input)

        self.context.add_user_message(user_input)
        self._budget_exhausted = False
        self._cancel = False
        tools_used = 0
        reflections = 0
        iterations = 0

        while True:
            iterations += 1
            if self._cancel:
                self.reporter.final_answer()
                self.reporter.summary()
                return self._STOPPED_MESSAGE
            if iterations > self.MAX_ITERATIONS:
                self.context.add_assistant_message(self._MAX_STEPS_MESSAGE)
                self.reporter.final_answer()
                self.reporter.summary()
                return self._MAX_STEPS_MESSAGE

            self.reporter.turn_begin()

            messages = self.context.get_messages() + self.extra_messages_provider()
            self.reporter.thinking()
            response = self.llm.chat(messages)
            self.reporter.thinking_done()

            if self._cancel:
                self.reporter.final_answer()
                self.reporter.summary()
                return self._STOPPED_MESSAGE

            tool_calls = self.parser.parse(response)
            self.reporter.tools_parsed(len(tool_calls))

            if not tool_calls:
                # 终答自检门：上下文未爆且检索可能未穷尽时，逼模型再试一轮。
                if (
                    not self._budget_exhausted
                    and reflections < self.MAX_REFLECTIONS
                    and self._needs_more_retrieval(response, tools_used)
                ):
                    self.context.add_assistant_message(response)
                    self.context.add_user_message(self._REFLECTION_PROMPT)
                    reflections += 1
                    self._log_reflection(reflections)
                    continue

                self.context.add_assistant_message(response)
                self.reporter.final_answer()
                self.reporter.summary()
                return response

            self.context.add_assistant_message(response)
            for tc in tool_calls:
                if tools_used >= self.MAX_TOOL_CALLS:
                    break
                result = self.registry.execute(tc.name, tc.params)
                self.reporter.tool_executed(tc.name, tc.params, result)
                self.context.add_tool_result(tc.name, result)
                tools_used += 1

            # 软上限：达到工具调用上限后，通知模型直接作答并跳过自检门，
            # 避免它继续无意义地调工具刷预算。硬上限 MAX_ITERATIONS 兜底。
            if tools_used >= self.MAX_TOOL_CALLS and not self._budget_exhausted:
                self._budget_exhausted = True
                self.context.add_user_message(
                    "[System notice: 已达工具调用上限，请基于已掌握的信息直接给出最终回答，不要再调用工具读取新内容。]"
                )

            self._check_budget()

    def _needs_more_retrieval(self, response: str, tools_used: int) -> bool:
        """判断模型是否过早收尾：本轮没检索过，或回答带『认输/凭先验知识』的措辞。"""
        if tools_used == 0:
            return True
        return (
            any(m in response for m in self._GIVEUP_MARKERS)
            or any(m in response for m in self._KNOWLEDGE_MARKERS)
        )

    def _check_budget(self):
        """三档分层调度。每轮按 auto > micro > snip 倒序判定，命中即停。

        critical 兜底放在最后：所有压缩都跑完仍超 critical_threshold 时，注入终结提示。
        用 _budget_exhausted 守卫，避免每轮重复注入通知（通知落在 auto 保留窗口里会越压越涨）。
        """
        cfg = self.compaction
        avail = cfg.context_budget_tokens - cfg.reserved_output_tokens
        used = self.context.total_tokens()
        ratio = used / avail if avail > 0 else 1.0

        if ratio > cfg.auto_threshold:
            saved = auto_compact(self.context, self.llm, cfg.keep_recent_turns)
            self._log_compact("auto", saved, used)
        elif ratio > cfg.micro_threshold:
            saved = micro_compact(self.context, self.llm, cfg.micro_summarize_count)
            self._log_compact("micro", saved, used)
        elif ratio > cfg.snip_threshold:
            saved = snip_compact(self.context, cfg.single_msg_max_tokens)
            if saved > 0:
                self._log_compact("snip", saved, used)

        if (
            not self._budget_exhausted
            and self.context.total_tokens() > avail * cfg.critical_threshold
        ):
            # 上下文将满是唯一合理的提前终止：置位后跳过自检门，避免与"别再读了"互相拉扯。
            self._budget_exhausted = True
            self.context.add_user_message(
                "[System notice: 上下文将满，请基于已掌握的信息直接给出最终回答，不要再调用工具读取新内容。]"
            )

    @staticmethod
    def _log_reflection(round_no: int):
        """自检门触发只记日志，不污染对话语义。"""
        logger.debug("[reflect:%s] 检索可能未穷尽，要求模型继续检索", round_no)

    @staticmethod
    def _log_compact(mode: str, saved: int, used_before: int):
        """压缩动作只记日志，不写回 messages，避免压缩通知本身又把上下文撑满。"""
        logger.debug("[compact:%s] before=%s saved≈%s tokens", mode, used_before, saved)
