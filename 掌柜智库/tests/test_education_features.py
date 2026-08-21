# ==================== AI修改 开始 ====================
# 教育知识库与多会话专项测试。
# 这些测试先定义用户能看到的结果：课程/题目必须结构化，多会话标题必须稳定。
# 这样后续改解析器、接口和前端时，不会只验证“代码能跑”，却漏掉教育需求。
# ==================== AI修改 结束 ====================
from pathlib import Path

from atguigu.edu_process.edu_parsers import parse_course_md, parse_question_md
from atguigu.query_process.nodes.node_search_embedding import (
    education_collection_is_available,
    select_existing_output_fields,
)
from atguigu.tool.session_catalog import (
    build_session_record,
    merge_session_catalog_rows,
    normalize_session_title,
)
from atguigu.web.api.education_service import (
    build_course_summary,
    build_question_summary,
    collect_education_import_inputs,
)
from atguigu.query_process.nodes.node_answer_output import (
    ANSWER_PROMPT,
    fit_prompt_fields,
    trim_history_content,
)
from atguigu.config.config import ModelConfig


def test_course_parser_returns_structured_education_metadata(tmp_path: Path):
    # 用最小课程样本覆盖需求中的课程名、编码、章节和学习信息。
    source = tmp_path / "课程介绍.md"
    source.write_text(
        """# 课程
## RAG 入门班
- **系列编码**: rag_foundation
- **描述**: 面向初学者的检索增强生成课程
- **课程分类**: 人工智能 / RAG
- **适合人群**: 在校生, 求职者
- **学习目标**: 掌握RAG基础
### 课程
- **文档切分与向量检索**
  - 编码: rag_foundation_m1, 课时: 8, 学时: 16.00
  - 描述: 完成一个知识库项目实战
""",
        encoding="utf-8",
    )

    chunk = parse_course_md(str(source))[0]

    assert chunk["course_name"] == "RAG 入门班"
    assert chunk["course_code"] == "rag_foundation"
    assert chunk["chapter_name"] == "文档切分与向量检索"
    assert chunk["course_category"] == "人工智能 / RAG"
    assert chunk["target_users"] == "在校生, 求职者"
    assert chunk["learning_goals"] == "掌握RAG基础"
    assert chunk["project_name"] == "知识库项目实战"
    assert chunk["source_path"] == str(source)


def test_question_parser_returns_structured_question_metadata(tmp_path: Path):
    # 一题一个 chunk，且题干、选项、答案、解析仍然完整保留在 content 中。
    source = tmp_path / "题目资料.md"
    source.write_text(
        """# 题目
## RAG基础题库
- 题库编码: rag_bank
### rag_bank_q001
- **题型**: 单选题
- **题干**: RAG中检索的作用是什么？
- **选项**:
A. 提供参考资料
B. 删除资料
- **答案**: A
- **解析**: 检索负责找出相关知识片段。
""",
        encoding="utf-8",
    )

    chunk = parse_question_md(str(source))[0]

    assert chunk["question_bank_name"] == "RAG基础题库"
    assert chunk["question_bank_code"] == "rag_bank"
    assert chunk["question_code"] == "rag_bank_q001"
    assert chunk["question_type"] == "单选题"
    assert "答案" in chunk["content"]
    assert "解析" in chunk["content"]


def test_session_title_is_human_readable_and_bounded():
    title = normalize_session_title("  请介绍一下掌柜智库的文档导入流程，以及图片如何展示？  ")
    record = build_session_record("session-001", title, 123.0)

    assert title.endswith("？")
    assert len(title) <= 32
    assert record == {
        "session_id": "session-001",
        "title": title,
        "updated_ts": 123.0,
    }


def test_structured_summaries_keep_source_and_question_fields():
    course = build_course_summary({
        "title": "RAG 入门班",
        "course_code": "rag_foundation",
        "chapter_name": "向量检索",
        "source_path": "课程介绍.md",
    })
    question = build_question_summary({
        "item_name": "RAG基础题库",
        "question_bank_code": "rag_bank",
        "code": "rag_bank_q001",
        "q_type": "单选题",
        "content": "题干\\n答案",
    })

    assert course["course_name"] == "RAG 入门班"
    assert course["source_path"] == "课程介绍.md"
    assert question["question_bank_name"] == "RAG基础题库"
    assert question["question_code"] == "rag_bank_q001"
    assert question["question_type"] == "单选题"


# ==================== AI修改 开始 ====================
# 教育资料允许只上传课程或只上传题库，前端不应强制用户凑齐两份文件。
# ==================== AI修改 结束 ====================
def test_education_import_accepts_one_source_file():
    assert collect_education_import_inputs("课程介绍.md", None) == [
        ("course", "课程介绍.md")
    ]
    assert collect_education_import_inputs(None, "题目资料.md") == [
        ("question", "题目资料.md")
    ]


# ==================== AI修改 开始 ====================
# Milvus教育表尚未创建时，查询节点应该返回空召回并让上层给出可读提示，
# 不能把 collection not found 直接冒泡成整条任务异常。
# ==================== AI修改 结束 ====================
def test_missing_education_collection_is_detected_before_search():
    class FakeMilvusClient:
        def has_collection(self, collection_name):
            return False

    assert education_collection_is_available(
        FakeMilvusClient(), "chunks_db_education"
    ) is False


# ==================== AI修改 开始 ====================
# 旧教育集合可能缺少后来新增的结构化字段，查询字段必须按实际schema取交集。
# ==================== AI修改 结束 ====================
def test_output_fields_are_filtered_by_existing_collection_schema():
    class FakeMilvusClient:
        def describe_collection(self, collection_name):
            return {"fields": [{"name": "id"}, {"name": "content"}]}

    assert select_existing_output_fields(
        FakeMilvusClient(),
        "chunks_db_education",
        ["id", "content", "course_name"],
    ) == ["id", "content"]


# ==================== AI修改 开始 ====================
# Mongo目录暂时不可用时，进程内兜底目录也必须保留多个会话，
# 新建会话不能把旧会话从界面列表中覆盖掉。
# ==================== AI修改 结束 ====================
def test_session_catalog_merge_keeps_multiple_local_sessions():
    rows = merge_session_catalog_rows(
        remote_rows=[],
        local_rows=[
            {"session_id": "s2", "title": "第二个会话", "updated_ts": 2},
            {"session_id": "s1", "title": "第一个会话", "updated_ts": 1},
        ],
    )

    assert [row["session_id"] for row in rows] == ["s2", "s1"]


# ==================== AI修改 开始 ====================
# 查询节点也必须像导入节点一样记录自己的执行耗时，前端时间线才能显示真实数据。
# ==================== AI修改 结束 ====================
def test_query_node_base_records_node_duration(monkeypatch):
    import atguigu.query_process.base as query_base

    duration_calls = []

    class DemoNode(query_base.NodeBase):
        name = "demo_query_node"

        def process(self, state):
            return {"ok": True}

    monkeypatch.setattr(query_base, "add_running_task", lambda *args: None)
    monkeypatch.setattr(query_base, "add_done_task", lambda *args: None)
    monkeypatch.setattr(query_base, "put_data", lambda *args, **kwargs: None)
    monkeypatch.setattr(query_base, "get_task_info", lambda *args: {})
    monkeypatch.setattr(
        query_base,
        "add_node_duration",
        lambda task_id, node_name, duration: duration_calls.append(
            (task_id, node_name, duration)
        ),
        raising=False,
    )

    assert DemoNode()({"task_id": "task-001"}) == {"ok": True}
    assert duration_calls[0][0:2] == ("task-001", "demo_query_node")
    assert duration_calls[0][2] >= 0


# ==================== AI修改 开始 ====================
# 状态卡片必须有实时总耗时、步骤计数和可读的完成耗时文案，防止只显示“正在检索”。
# ==================== AI修改 结束 ====================
def test_query_status_panel_contains_elapsed_time_ui():
    page = Path(__file__).parents[1] / "atguigu" / "web" / "page" / "index.html"
    html = page.read_text(encoding="utf-8")

    assert "proc-elapsed" in html
    assert "proc-step-count" in html
    assert "startProcElapsedTimer" in html


# ==================== AI修改 开始 ====================
# 深度讲解保留6144 token硬上限，同时由软收束长度控制，不再依赖8192的无限扩写空间。
# ==================== AI修改 结束 ====================
def test_answer_generation_budget_and_memory_window_are_expanded():
    assert ModelConfig.LLM_MAX_TOKENS == 6144
    assert ModelConfig.ANSWER_SOFT_MAX_CHARS > 0
    assert ModelConfig.ANSWER_DETAILED_SOFT_MAX_CHARS > ModelConfig.ANSWER_SOFT_MAX_CHARS
    assert ModelConfig.QUERY_HISTORY_LIMIT >= 20
    assert ModelConfig.ANSWER_MAX_CONTEXT_CHARS >= 18000


def test_education_import_runtime_path_is_outside_project_directory():
    from atguigu.config.config import build_runtime_temp_path

    workspace = Path(__file__).parents[1]
    task_path = build_runtime_temp_path("task-001", "2026-08-21")

    assert task_path == task_path.parents[2] / "education_imports" / "2026-08-21" / "task-001"
    assert workspace not in task_path.parents


# ==================== AI修改 开始 ====================
# 扩大记忆不能无上限拼接；超长时保留最近内容，避免把当前问题挤出上下文。
# ==================== AI修改 结束 ====================
def test_history_trim_keeps_latest_context():
    history = "较早对话\n" * 2000 + "\n最新问题：Java语法和面向对象"
    trimmed = trim_history_content(history, 200)

    assert len(trimmed) <= 200
    assert "最新问题：Java语法和面向对象" in trimmed


# ==================== AI修改 开始 ====================
# 并发导入时，BGE-M3 的实际向量化调用必须互斥；否则多个线程同时进入
# PyTorch/CUDA 原生代码，可能出现 Windows 访问冲突并导致整个后端进程退出。
# ==================== AI修改 结束 ====================
def test_embedding_calls_are_serialized_for_shared_model(monkeypatch):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace

    import numpy as np

    import atguigu.tool.bgem3_create_tool as embedding_tool

    active_calls = 0
    max_active_calls = 0
    active_lock = threading.Lock()

    class FakeEmbeddingModel:
        def encode_documents(self, texts):
            nonlocal active_calls, max_active_calls
            with active_lock:
                active_calls += 1
                max_active_calls = max(max_active_calls, active_calls)
            time.sleep(0.05)
            with active_lock:
                active_calls -= 1
            return {
                "dense": [np.array([1.0])],
                "sparse": [SimpleNamespace(
                    indices=np.array([0]),
                    data=np.array([1.0]),
                )],
            }

    monkeypatch.setattr(embedding_tool, "bgem3_model", FakeEmbeddingModel())
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: embedding_tool.vectorize_texts(["并发测试"]), range(2)))

    assert max_active_calls == 1


# ==================== AI修改 开始 ====================
# 后端进程原生崩溃后，前端请求会连续失败；页面必须把卡片标记为连接中断，
# 不能永远停留在“主体识别/处理中”。
# ==================== AI修改 结束 ====================
def test_import_status_polling_handles_backend_disconnect():
    page = Path(__file__).parents[1] / "atguigu" / "web" / "page" / "index.html"
    html = page.read_text(encoding="utf-8")

    assert "consecutiveNetworkErrors" in html
    assert "后端连接中断" in html


# ==================== AI修改 开始 ====================
# 首条提问必须真正调用会话重命名接口，不能只刷新仍然是“新会话”的目录。
# ==================== AI修改 结束 ====================
def test_first_query_updates_session_title_from_question():
    page = Path(__file__).parents[1] / "atguigu" / "web" / "page" / "index.html"
    html = page.read_text(encoding="utf-8")

    assert "ensureFirstSessionTitle" in html
    assert "body: JSON.stringify({title: text})" in html


# ==================== AI修改 开始 ====================
# 广泛问题不能把检索、记忆、提示词和输出预算全部叠加到模型上下文之外；
# 动态预算必须裁剪旧内容，同时保留当前问题和最新历史。
# ==================== AI修改 结束 ====================
def test_prompt_budget_trims_context_and_history_together():
    context = "高相关资料：Java语法与面向对象。" * 6000
    history = "较早历史对话。" * 4000 + "\n最新问题：请继续讲异常处理"
    question = "请详细系统讲解 Java 语法"

    fitted_context, fitted_history = fit_prompt_fields(
        ANSWER_PROMPT,
        context=context,
        history=history,
        question=question,
        item_names="Java",
    )
    prompt = ANSWER_PROMPT.format(
        context=fitted_context,
        history=fitted_history,
        question=question,
        item_names="Java",
    )

    assert len(prompt) <= 21000
    assert fitted_context.startswith("高相关资料")
    assert "最新问题：请继续讲异常处理" in fitted_history


# ==================== AI修改 开始 ====================
# 流式模型达到 max_tokens 时，前端必须收到明确的“已完成部分”收尾提示。
# ==================== AI修改 结束 ====================
def test_length_finish_reason_is_detected():
    from atguigu.query_process.nodes.node_answer_output import is_length_finish_reason

    assert is_length_finish_reason("length") is True
    assert is_length_finish_reason("stop") is False


# ==================== AI修改 开始 ====================
# 回归测试：答案不能只依赖6144 token的硬上限，而要根据问题类型设置软收束长度。
# 详细问题允许比普通问题展开更多，但达到完整句/段落后应主动结束，避免无止境扩写。
# ==================== AI修改 结束 ====================
def test_answer_output_policy_has_reasonable_soft_stop():
    from atguigu.query_process.nodes.node_answer_output import (
        get_answer_soft_max_chars,
        should_soft_stop_answer,
    )

    normal_limit = get_answer_soft_max_chars("Java中的接口是什么？", "knowledge")
    detailed_limit = get_answer_soft_max_chars("请详细深入系统讲解Java语法", "knowledge")

    assert detailed_limit > normal_limit
    assert detailed_limit < 6144 * 2
    assert should_soft_stop_answer("Java语法说明。" * 1000, normal_limit, 600)
    assert not should_soft_stop_answer("Java语法说明。" * 10, normal_limit, 600)


# ==================== AI修改 开始 ====================
# 题目检索不能先承诺“9道题”再逐题长篇展开，否则容易在某道题中间撞上6144硬上限。
# 本轮应该限制题目数量、使用紧凑格式，并为题目分支设置独立软收束长度。
# ==================== AI修改 结束 ====================
def test_question_answer_scope_prevents_incomplete_multi_question_output():
    from atguigu.query_process.nodes.node_answer_output import (
        get_answer_scope_instruction,
        get_answer_soft_max_chars,
    )

    instruction = get_answer_scope_instruction("question")
    question_limit = get_answer_soft_max_chars("客服话术", "question")

    assert "最多完整展示5道" in instruction
    assert "不要先承诺" in instruction
    assert question_limit <= 5200

# ==================== AI修改 开始 ====================
# 回归测试：软收束触发后必须关闭底层流，避免远端模型继续生成到硬上限。
# 这个测试使用本地假流，不访问真实模型，只验证“停止生成”的边界行为。
def test_stream_answer_closes_model_stream_after_soft_stop(monkeypatch):
    from types import SimpleNamespace

    import atguigu.query_process.nodes.node_answer_output as answer_output

    class FakeStream:
        def __init__(self):
            self.closed = False
            self.consumed = 0

        def __iter__(self):
            for _ in range(20):
                self.consumed += 1
                yield SimpleNamespace(content="这一段内容已经完整。")

        def close(self):
            self.closed = True

    class FakeLLM:
        def __init__(self, stream):
            self.stream_result = stream

        def stream(self, input):
            return self.stream_result

    stream = FakeStream()
    node = answer_output.NodeAnswerOutput()
    node._llm = FakeLLM(stream)
    monkeypatch.setattr(answer_output, "put_data", lambda *args, **kwargs: None)

    answer = node.stream_llm_answer(
        "task-soft-stop",
        "请回答这个问题",
        soft_max_chars=20,
        soft_stop_grace_chars=0,
    )

    assert "这一段内容已经完整。" in answer
    assert stream.consumed < 20
    assert stream.closed is True
# ==================== AI修改 结束 ====================
