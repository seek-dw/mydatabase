# atguigu/query_process/nodes/node_answer_output.py
import re
import threading

from langchain.chat_models import init_chat_model

# ==================== AI修改 开始 ====================
# 同时读取 MinIO 配置，旧切片中的相对图片路径需要在答案阶段补成完整 URL。
# ==================== AI修改 结束 ====================
from atguigu.config.config import MinioConfig, ModelConfig
# ==================== AI修改 开始 ====================
# 新增导入：闲聊提示词CHAT_PROMPT、无结果兜底提示词NO_RESULT_PROMPT
from atguigu.config.prompt import ANSWER_PROMPT, CHAT_PROMPT, NO_RESULT_PROMPT
# ==================== AI修改 结束 ====================
from atguigu.query_process.base import NodeBase
from atguigu.query_process.state import QueryGraphState
from atguigu.tool.logger import logger
from atguigu.tool.mongo_client_tool import add_or_update_history, get_recent_history_list, get_session_summary, compress_session_history
from atguigu.tool.task_utils import put_data
# ==================== AI修改 开始 ====================
# 图片解析规则与导入节点共用，确保 Markdown/HTML 两种写法处理一致。
# ==================== AI修改 结束 ====================
from atguigu.tool.image_url_tool import (
    collect_image_references_from_chunks,
    extract_image_references,
    normalize_image_urls,
    resolve_image_reference,
)

# ==================== AI修改 开始 ====================
# 历史记忆裁剪：只在超过上限时从最早位置折叠，确保最新一轮对话永远保留。
# 这样既能扩大记忆窗口，又不会让历史无限增长挤掉当前问题和回答预算。
def trim_history_content(history_content: str, max_chars: int) -> str:
    if not history_content or max_chars <= 0:
        return ""
    if len(history_content) <= max_chars:
        return history_content
    marker = "【更早的历史已折叠】\n"
    keep_chars = max(0, max_chars - len(marker))
    return marker + history_content[-keep_chars:]


# ==================== AI修改 开始 ====================
# 根据模型总上下文窗口动态压缩“检索资料 + 历史记忆”。
# 估算采用偏保守的中文字符预算，并额外扣除输出token和安全余量，
# 防止只看单项上限却把完整prompt送超模型上下文。
def fit_prompt_fields(
    prompt_template: str,
    *,
    context: str,
    history: str,
    question: str,
    item_names: str,
) -> tuple[str, str]:
    fixed_prompt = prompt_template.format(
        context="",
        history="",
        question=question or "",
        item_names=item_names or "",
    )
    available_tokens = max(
        2048,
        ModelConfig.LLM_CONTEXT_WINDOW_TOKENS
        - ModelConfig.LLM_MAX_TOKENS
        - ModelConfig.LLM_PROMPT_SAFETY_TOKENS,
    )
    # 中文通常接近1字符/token，乘0.85给tokenizer差异留余量。
    prompt_char_budget = max(8000, int(available_tokens * 0.85))
    fields_budget = max(0, prompt_char_budget - len(fixed_prompt))

    desired_context = min(
        len(context or ""), ModelConfig.ANSWER_MAX_CONTEXT_CHARS
    )
    desired_history = min(
        len(history or ""), ModelConfig.ANSWER_MAX_HISTORY_CHARS
    )

    # 先给高相关检索资料约65%的空间，剩余空间给历史；两边不足时再互相回填。
    context_limit = min(desired_context, int(fields_budget * 0.65))
    history_limit = min(desired_history, fields_budget - context_limit)
    remaining = fields_budget - context_limit - history_limit
    if remaining > 0:
        extra_context = min(remaining, desired_context - context_limit)
        context_limit += extra_context
        remaining -= extra_context
        history_limit += min(remaining, desired_history - history_limit)

    fitted_context = (context or "")[:context_limit]
    fitted_history = trim_history_content(history or "", history_limit)
    return fitted_context, fitted_history


def is_length_finish_reason(reason: object) -> bool:
    """判断流式模型是否因为达到输出长度上限而结束。"""
    return str(reason or "").lower() in {
        "length",
        "max_tokens",
        "token_limit",
    }


# ==================== AI修改 开始 ====================
# 让回答长度由“问题类型”决定：普通问题及时收束，明确要求详细讲解时
# 允许更长，但不会因为提示词写了“完整”就一直生成到6144 token。
def get_answer_soft_max_chars(question: str, query_type: str = "") -> int:
    if query_type == "chitchat":
        return min(ModelConfig.ANSWER_SOFT_MAX_CHARS, 1600)
    detailed_pattern = re.compile(
        r"详细|深入|系统|全面|完整|原理|逐步|教程|从基础|深度讲解"
    )
    if detailed_pattern.search(question or ""):
        return ModelConfig.ANSWER_DETAILED_SOFT_MAX_CHARS
    return ModelConfig.ANSWER_SOFT_MAX_CHARS


def should_soft_stop_answer(
    answer: str,
    soft_max_chars: int,
    grace_chars: int,
) -> bool:
    """达到软上限且出现完整句边界，或超过宽限区时，允许流式收束。"""
    if not answer or soft_max_chars <= 0 or len(answer) < soft_max_chars:
        return False

    # 优先等到最近的句号/问号/感叹号/分号/换行，避免截断半句话。
    boundary_chars = "。！？；\n"
    boundary_start = max(0, soft_max_chars - 300)
    last_boundary = max(answer.rfind(char) for char in boundary_chars)
    if last_boundary >= boundary_start:
        return True

    # 模型长时间不输出标点时使用宽限区兜底，防止流式请求一直不结束。
    return len(answer) >= soft_max_chars + max(0, grace_chars)
# ==================== AI修改 结束 ====================
# ==================== AI修改 结束 ====================


class NodeAnswerOutput(NodeBase):
    """
    节点功能: 答案生成
    """

    # 覆盖基类的 name 属性，标识节点名称
    name: str = "node_answer_output"

    # ==================== AI修改 开始 ====================
    # LLM客户端懒加载缓存: 原来每轮回答都init_chat_model重建客户端(白白多一次
    # 连接/鉴权开销),改成类级缓存只初始化一次,后续所有轮次复用
    _llm = None
    # ==================== AI修改 结束 ====================

    # ==================== AI修改 开始 ====================
    # 抽取公共方法：流式调用LLM并逐段推送,闲聊分支和检索生成分支共用
    # context_chars/history_chars/question_chars: prompt各组成的字符数, 用于前端进度条
    #   分段显示"记忆X字·检索X字", 让用户看到记忆压缩的效果
    # summary_active: 该会话是否已有长期记忆摘要(压缩过), 前端显示"已压缩"标签
    def stream_llm_answer(self, task_id: str, prompt: str, *,
                          context_chars=0, history_chars=0, question_chars=0,
                          summary_active=False, soft_max_chars=None,
                          soft_stop_grace_chars=None) -> str:
        # ==================== AI修改 开始 ====================
        # 推送当前prompt的上下文占用给前端, 输入框上方进度条据此显示。
        # 改进: 不再只给一个总字数, 而是分解成 [检索context + 记忆history + 问题],
        # 前端分段显示, 与记忆直接挂钩——用户能看到"记忆占了多少""检索占了多少"
        # 以及长期摘要是否已激活(压缩过), 这才是"和记忆挂钩"的进度条。
        try:
            _chars = len(prompt)
            _tokens = int(_chars / 1.5)
            # ==================== AI修改 开始 ====================
            # 进度条上限跟随扩大后的上下文展示预算，避免大回答一开始就显示100%。
            _limit = ModelConfig.ANSWER_CONTEXT_DISPLAY_LIMIT
            # ==================== AI修改 结束 ====================
            put_data(task_id, "context_info", {
                "chars": _chars,
                "tokens": _tokens,
                "limit": _limit,
                "pct": min(100, int(_chars * 100 / _limit)),
                # ==================== AI修改 开始 ====================
                # 组成分解: 让进度条与记忆挂钩
                "context_chars": context_chars,   # 检索到的知识库内容
                "history_chars": history_chars,   # 对话记忆(含长期摘要)
                "question_chars": question_chars,  # 当前问题
                "summary_active": summary_active,  # 长期记忆摘要是否已激活
                # ==================== AI修改 结束 ====================
            })
        except Exception:
            pass
        # ==================== AI修改 结束 ====================
        # AI修改: 懒加载缓存LLM客户端(与node_item_name_confirm同款优化)
        if self._llm is None:
            # ==================== AI修改 开始 ====================
            # 输出token上限改为配置项，默认8192，解决详细讲解输出到一半停止的问题。
            # 如果当前模型上下文窗口较小，可在根目录 .env 中把 LLM_MAX_TOKENS 调低。
            # ==================== AI修改 结束 ====================
            self._llm = init_chat_model(
                model = ModelConfig.LLM_MODEL_NAME,
                model_provider="openai",
                api_key = ModelConfig.MODA_API_KEY,
                base_url = ModelConfig.VL_MODEL_BASE_URL,
                temperature = ModelConfig.VL_MODEL_TEMPERATURE,
                # ==================== AI修改 开始 ====================
                # 使用统一配置，避免某个节点仍然偷偷使用较小的默认输出限制。
                max_tokens = ModelConfig.LLM_MAX_TOKENS
                # ==================== AI修改 结束 ====================
            )
        llm = self._llm
        messages = [{"role":"user","content":prompt}]
        answer = ""
        finish_reason = None
        soft_stop_reached = False
        # ==================== AI修改 开始 ====================
        res = None
        # ==================== AI修改 结束 ====================
        try:
            #流式调用,返回生成器
            res = llm.stream(input = messages)
            for r in res:
                delta = r.content or ""
                if delta:
                    put_data(task_id, "delta", {"delta": delta})
                    answer += delta
                    # ==================== AI修改 开始 ====================
                    # 软上限只在完整句/段落边界收束；如果模型迟迟不给标点，
                    # 宽限一小段字符后也结束，避免答案无止境生成到硬上限。
                    if soft_max_chars and should_soft_stop_answer(
                        answer,
                        soft_max_chars,
                        soft_stop_grace_chars
                        if soft_stop_grace_chars is not None
                        else ModelConfig.ANSWER_SOFT_STOP_GRACE_CHARS,
                    ):
                        soft_stop_reached = True
                        break
                    # ==================== AI修改 结束 ====================
                # ==================== AI修改 开始 ====================
                # 不同OpenAI兼容服务可能把结束原因放在不同字段，逐块兼容读取。
                metadata = getattr(r, "response_metadata", {}) or {}
                additional = getattr(r, "additional_kwargs", {}) or {}
                finish_reason = (
                    metadata.get("finish_reason")
                    or additional.get("finish_reason")
                    or finish_reason
                )
                # ==================== AI修改 结束 ====================
            # ==================== AI修改 开始 ====================
            # 模型正常返回但达到max_tokens时，不会进入except；这里主动补充收尾。
            if soft_stop_reached and answer:
                notice = "\n\n（已完成本问题的核心内容，更多细节可以继续追问。）"
                put_data(task_id, "delta", {"delta": notice})
                answer += notice
            elif is_length_finish_reason(finish_reason) and answer:
                notice = "\n\n（回答已达到本轮输出上限，以上为已完成内容。）"
                put_data(task_id, "delta", {"delta": notice})
                answer += notice
            # ==================== AI修改 结束 ====================
        except Exception as e:
            # LLM流式调用失败(网络/超时)：已生成的部分照常返回,一段都没有则给出兜底话术,绝不静默崩溃
            logger.error(f"答案生成LLM流式调用失败: {e}")
            if not answer:
                answer = "抱歉，回答生成时出现了问题，请稍后重试。"
            else:
                # ==================== AI修改 开始 ====================
                # 已经生成部分内容时显式收尾，前端能看到完整的已生成答案，
                # 不会像网络断开后停在半句话，让用户误以为界面卡死。
                notice = "\n\n（生成连接中途结束，以上为已完成内容。）"
                put_data(task_id, "delta", {"delta": notice})
                answer += notice
                # ==================== AI修改 结束 ====================
        finally:
            # ==================== AI修改 开始 ====================
            # break 只能停止本地 for 循环，不能保证 HTTP 流被远端关闭；
            # 如果不主动 close，模型服务可能继续生成，直到消耗完 max_tokens。
            # 正常结束、软停止和异常退出都统一释放底层流，避免答案无止境生成。
            close_stream = getattr(res, "close", None)
            if callable(close_stream):
                try:
                    close_stream()
                except Exception as close_error:
                    # 关闭失败不覆盖已经生成的答案，只留下可排查的日志。
                    logger.warning(f"关闭答案生成流失败: {close_error}")
            # ==================== AI修改 结束 ====================
        return answer

    # 组装历史对话字符串(三个分支共用)
    # ==================== AI修改 开始 ====================
    # 记忆机制第二次重构(2026-08-20下午): 用户实测反馈"上一轮问完下一轮就不知道"
    # 第一版(A档记忆)的分层注入 [长期摘要+中期仅qa过滤+近期3轮原文] 过于复杂:
    #   - 中期过滤按 msg_type 丢记录, 一旦某轮被打上 chat 标签(确认引导/闲聊)就整轮消失
    #   - RECENT_KEEP=6 只保底3轮, 窗口太小
    #   - 实际数据里 assistant 记录还会因回答失败缺失, 过滤+缺失叠加 → 记忆严重断裂
    # 重构为简单可靠的两层:
    #   [长期摘要]  +  [最近20条原文全保留]
    # 最近20条(≈10轮) 无论 msg_type 一律原样注入, "上一轮问了什么" 100% 在上下文里。
    # 长期摘要负责更早对话的记忆, 由 compress_session_history(已加锁) 滚动生成。
    # ==================== AI修改 结束 ====================
    def make_history_content(self, state: QueryGraphState) -> str:
        session_id = state.get("session_id", "")
        try:
            # ==================== AI修改 开始 ====================
            # 最近20条原文全保留(≈10轮问答)，数量由统一配置控制。
            raw = get_recent_history_list(
                session_id,
                limit=ModelConfig.QUERY_HISTORY_LIMIT,
            )
            # ==================== AI修改 结束 ====================
        except Exception:
            raw = []
        raw_asc = list(reversed(raw)) if raw else []
        recent_content = "".join(f"{m.get('role','')}: {m.get('text','')}\n\n" for m in raw_asc)
        # 长期记忆摘要(更早对话的压缩要点, 已有机制)
        long_term = ""
        try:
            summary = get_session_summary(session_id)
            if summary:
                long_term = f"【长期记忆摘要(较早对话的要点)】\n{summary}\n\n"
        except Exception:
            pass
        # ==================== AI修改 开始 ====================
        # 记忆窗口扩大后统一裁剪最早内容，始终保留最新提问、回答和长期摘要。
        history_content = (long_term + "【近期对话】\n" + recent_content) if long_term else recent_content
        return trim_history_content(history_content, ModelConfig.ANSWER_MAX_HISTORY_CHARS)
        # ==================== AI修改 结束 ====================

    def process(self, state: QueryGraphState):
        """
        节点逻辑
        :param state: 工作流状态对象
        :return: 更新后的状态对象
        """
        # 1.拿到answer,根据answer有无进行下一步的判断
        # ==================== AI修改 开始 ====================
        # 原question: 有answer不是再给用户反馈吗,这不能算作最终的answer吧?
        # 答案与改进: 这里的answer确实是"反馈话术"(如引导确认),不是知识库答案,
        # 但对用户来说它就是本轮的最终回复,推送后本轮对话即结束,所以语义上没错。
        # 不过原代码有个真实缺陷: 反馈话术没有写入聊天历史,导致多轮对话时
        # 模型看不到自己上一轮说过"请确认您要咨询的商品是xxx",历史会话断裂。
        # 改进: 推送反馈的同时也保存进历史,保持会话完整性
        answer = state.get("answer")
        task_id = state.get("task_id")
        session_id = state.get("session_id")
        original_query = state.get("original_query")

        # ========== 分支1：需要用户确认/引导的反馈话术，直接推送，不调LLM ==========
        if answer:
            # AI修改: 反馈话术也写入历史,多轮追问时模型能接得上上文
            add_or_update_history(
                session_id=session_id, role="assistant", text=answer,
                rewritten_query=original_query, item_names=[], image_urls=[],
                msg_type="chat"
            )
            # ==================== AI修改 开始 ====================
            # final 同时携带答案和空图片列表，前端不必为不同分支写特殊判断。
            # ==================== AI修改 结束 ====================
            put_data(task_id, "final", {"answer": answer, "image_urls": []})
            return {"answer": answer}

        history_content = self.make_history_content(state)
        query_type = state.get("query_type", "")
        chunks = state.get("reranked_docs") or []

        # ========== 分支2：闲聊 或 检索结果为空 → 带历史的流式通用对话 ==========
        # 闲聊：用CHAT_PROMPT正常聊天
        # 检索为空：用NO_RESULT_PROMPT兜底说明"知识库没找到,以下仅供参考"
        if query_type == "chitchat" or not chunks:
            template = CHAT_PROMPT if query_type == "chitchat" else NO_RESULT_PROMPT
            # ==================== AI修改 开始 ====================
            # 闲聊/无结果分支也走总上下文预算，避免历史过长把问题或输出挤掉。
            _, history_content = fit_prompt_fields(
                template,
                context="",
                history=history_content,
                question=original_query,
                item_names="",
            )
            prompt = template.format(history=history_content, question=original_query)
            # ==================== AI修改 结束 ====================
            # ==================== AI修改 开始 ====================
            # 传入组成分解: 闲聊无检索context, 记忆+问题两段; summary_active 由
            # history_content 是否以"【长期记忆摘要"开头判断(无需额外查DB)
            _summary_active = history_content.startswith("【长期记忆摘要")
            answer = self.stream_llm_answer(
                task_id, prompt,
                context_chars=0,
                history_chars=len(history_content),
                question_chars=len(original_query or ""),
                summary_active=_summary_active,
                soft_max_chars=get_answer_soft_max_chars(
                    original_query or "", query_type
                ),
            )
            # ==================== AI修改 开始 ====================
            # 历史写入加固: 原来 if answer 才写, 一旦LLM流式失败返回空,
            # assistant记录缺失 → 下一轮历史链断裂(实测mongo用户会话只有1条user记录)。
            # 现在无条件写入, answer为空时用兜底话术占位, 保证user/assistant成对出现。
            # ==================== AI修改 结束 ====================
            _mt = "chat" if query_type == "chitchat" else "qa"
            add_or_update_history(
                session_id=session_id, role="assistant",
                text=answer or "抱歉，回答生成时出现了问题，请稍后重试。",
                rewritten_query=original_query, item_names=[], image_urls=[],
                msg_type=_mt
            )
            # ==================== AI修改 开始 ====================
            # 无检索结果或闲聊没有知识库图片，但 final 仍返回完整答案，
            # 避免前端只能依赖 delta 拼接作为唯一答案来源。
            # ==================== AI修改 结束 ====================
            put_data(task_id, "final", {
                "answer": answer or "",
                "image_urls": [],
            })
            # 长期记忆: 异步压缩超阈值的早期对话(不阻塞响应)
            threading.Thread(target=compress_session_history, args=(session_id, self._llm), daemon=True).start()
            return {"answer": answer}

        # ========== 分支3：正常检索生成（原有逻辑 + 来源引用增强） ==========
        chunk_content = ""
        for chunk in chunks:
            title = chunk.get("title")
            content = chunk.get("content")
            url = chunk.get("url")
            source = chunk.get("source")
            # 拼接教育元数据作为来源信息,让模型能按【来源】格式引用
            source_name = chunk.get("source_name") or ""
            code = chunk.get("code") or ""
            q_type = chunk.get("q_type") or ""
            meta_parts = [p for p in [source_name, code, q_type] if p]
            meta_str = f"（来源: {','.join(meta_parts)}）" if meta_parts else ""
            content = f"[{title}] [{url}] [{source}]{meta_str}\n{content}\n\n"
            chunk_content += content

        # ==================== AI修改 开始 ====================
        # 原question: 大模型一次接收的最大长度一般是多少,如果把问题截掉了没事吗?
        # 答案与改进: 大模型上下文一般是几万到几十万token,真正要防的是超长context。
        # 原代码的写法有个隐患: prompt是 [context][history][question] 顺序拼的,
        # 盲目的 prompt[:10000] 从头截,截掉的恰恰是末尾的question和item_names——
        # 相当于把"问题"砍了只留资料,模型不知道该答什么。
        # 改进: 在拼接前就限制context长度,chunks已按重排分数从高到低排序,
        # 从尾部(相关性最低的chunk)开始丢弃,直到context装得下,question永远完整
        # ==================== AI修改 开始 ====================
        # 检索上下文扩大到默认18000字符，保留更多相关资料支撑详细回答。
        MAX_CONTEXT_CHARS = ModelConfig.ANSWER_MAX_CONTEXT_CHARS
        # ==================== AI修改 结束 ====================
        while len(chunk_content) > MAX_CONTEXT_CHARS and len(chunks) > 1:
            chunks = chunks[:-1]  # 丢弃重排分数最低的chunk
            chunk_content = ""
            for chunk in chunks:
                title = chunk.get("title")
                content = chunk.get("content")
                url = chunk.get("url")
                source = chunk.get("source")
                source_name = chunk.get("source_name") or ""
                code = chunk.get("code") or ""
                q_type = chunk.get("q_type") or ""
                meta_parts = [p for p in [source_name, code, q_type] if p]
                meta_str = f"（来源: {','.join(meta_parts)}）" if meta_parts else ""
                chunk_content += f"[{title}] [{url}] [{source}]{meta_str}\n{content}\n\n"
        # 极端情况: 单个chunk就超长,截chunk本体,但question部分绝不动
        if len(chunk_content) > MAX_CONTEXT_CHARS:
            chunk_content = chunk_content[:MAX_CONTEXT_CHARS]
        # ==================== AI修改 结束 ====================

        item_names = state.get("item_names") or []
        item_names_str = ",".join(item_names)
        rewritten_query = state.get("rewritten_query")

        # ==================== AI修改 开始 ====================
        # 最终组装前再次按“总上下文预算”压缩检索和历史，确保广泛问题不会
        # 因两项局部上限叠加而超过模型上下文窗口；问题和实体字段保持完整。
        chunk_content, history_content = fit_prompt_fields(
            ANSWER_PROMPT,
            context=chunk_content,
            history=history_content,
            question=rewritten_query,
            item_names=item_names_str,
        )
        # ==================== AI修改 结束 ====================

        prompt = ANSWER_PROMPT.format(
            context = chunk_content,
            history = history_content,
            question = rewritten_query,
            item_names = item_names_str
            )

        #调用大模型(改为公共流式方法)
        # ==================== AI修改 开始 ====================
        # 传入组成分解: 检索context + 记忆history + 问题question 三段
        # summary_active 判断长期记忆摘要是否已激活(与记忆压缩直接挂钩)
        _summary_active = history_content.startswith("【长期记忆摘要")
        answer = self.stream_llm_answer(
            task_id, prompt,
            context_chars=len(chunk_content),
            history_chars=len(history_content),
            question_chars=len(rewritten_query or original_query or ""),
            summary_active=_summary_active,
            soft_max_chars=get_answer_soft_max_chars(
                rewritten_query or original_query or "", query_type
            ),
        )
        # ==================== AI修改 结束 ====================

        # ==================== AI修改 开始 ====================
        # 新数据通常已经是完整 MinIO URL；旧切片可能仍是 images/xxx.jpg。
        # 统一转换后再返回，避免前端收到相对路径而无法加载。
        # ==================== AI修改 开始 ====================
        # 用户明确索要流程图/图片时，最终重排结果可能只留下文字说明；
        # 从本轮 RRF 候选补抓带图片的切片，避免模型说“有4张图”但 final 没有 URL。
        fallback_chunks = state.get("rrf_chunks") or []
        primary_references = collect_image_references_from_chunks(
            chunks, [], original_query or rewritten_query or ""
        )
        fallback_references = collect_image_references_from_chunks(
            [], fallback_chunks, original_query or rewritten_query or ""
        )
        allowed_references = set(primary_references + fallback_references)
        image_source_chunks = list(chunks)
        if fallback_references:
            image_source_chunks.extend(fallback_chunks)
        # ==================== AI修改 结束 ====================

        image_candidates = []
        for doc in image_source_chunks:
            text = doc.get("content") or ""
            file_title = doc.get("file_title") or ""
            for reference in extract_image_references(text):
                if reference not in allowed_references:
                    continue
                if reference.startswith(("http://", "https://")):
                    image_candidates.append(reference)
                elif file_title:
                    image_candidates.append(resolve_image_reference(
                        reference,
                        file_title,
                        MinioConfig.MINIO_ENDPOINT,
                        MinioConfig.MINIO_BUCKET_NAME,
                        MinioConfig.MINIO_IMG_DIR,
                    ))
        images = normalize_image_urls(image_candidates)
        # 记录召回切片中的图片数量，便于区分“没有召回图片”和“前端加载失败”。
        logger.info(f"答案图片提取完成: 召回{len(chunks)}个切片，返回{len(images)}张图片")
        # ==================== AI修改 结束 ====================

        #保存历史
        # ==================== AI修改 开始 ====================
        # 历史写入加固(与分支2一致): 无条件写入, answer为空用兜底话术占位,
        # 保证 user/assistant 成对, 下一轮记忆链不断裂
        # ==================== AI修改 结束 ====================
        add_or_update_history(
            session_id = session_id,
            role = "assistant",
            text = answer or "抱歉，回答生成时出现了问题，请稍后重试。",
            rewritten_query = rewritten_query,
            item_names = item_names,
            image_urls = images,
            msg_type = "qa"
        )
        # ==================== AI修改 开始 ====================
        # final 同时携带完整答案和图片列表，前端可以直接渲染最终结果。
        # ==================== AI修改 结束 ====================
        put_data(task_id, "final", {
            "answer": answer or "",
            "image_urls": images,
        })
        # 长期记忆: 异步压缩超阈值的早期对话(不阻塞响应, self._llm已在stream_llm_answer初始化)
        if self._llm is not None:
            threading.Thread(target=compress_session_history, args=(session_id, self._llm), daemon=True).start()
        return {
            "answer":answer
        }
        # ==================== AI修改 结束 ====================


