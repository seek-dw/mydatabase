# ==================== AI修改 开始 ====================
# 主体识别节点的纯函数回归测试。
# 不连接真实模型或 Milvus，只固定输入证据、名称规范化和过滤表达式的行为。
from atguigu.import_process.nodes.node_item_name_recognition import (
    NodeItemNameRecognition,
)
# ==================== AI修改 结束 ====================


# ==================== AI修改 开始 ====================
def test_item_name_evidence_keeps_document_titles_across_long_documents():
    chunks = [
        {"title": "产品总览", "content": "这是开头内容。"},
        {"title": "安装说明", "content": "这是中间章节。"},
        {"title": "故障排查", "content": "这是结尾内容。"},
    ]

    evidence = NodeItemNameRecognition.build_item_name_evidence(chunks, "设备安全手册")

    assert "设备安全手册" in evidence
    assert "产品总览" in evidence
    assert "安装说明" in evidence
    assert "故障排查" in evidence


def test_normalize_item_name_removes_model_prefix_but_preserves_internal_spaces():
    item_name = NodeItemNameRecognition.normalize_item_name(
        "主体名称：Python 3.12\n",
        fallback="课程资料",
        evidence="Python 3.12 是本章使用的运行环境。",
    )

    assert item_name == "Python 3.12"


def test_normalize_item_name_falls_back_when_model_invents_unsupported_name():
    item_name = NodeItemNameRecognition.normalize_item_name(
        "一个面向企业的智能办公平台",
        fallback="企业办公系统手册",
        evidence="本文介绍打印机的安装和维护方法。",
    )

    assert item_name == "企业办公系统手册"


def test_escape_milvus_string_escapes_backslashes_and_quotes():
    value = "A\\B'款\"版"

    assert NodeItemNameRecognition.escape_milvus_string(value) == "A\\\\B\\'款\\\"版"
# ==================== AI修改 结束 ====================
