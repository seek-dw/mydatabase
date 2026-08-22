# ==================== AI修改 开始 ====================
"""统一知识切片存储的行为测试。"""

from atguigu.tool.knowledge_chunk_store import (
    KnowledgeChunkStore,
    build_document_id,
)
from atguigu.tool.milvus_client_create import build_item_name_expr
from atguigu.web.api import knowledge_service


class FakeMilvusClient:
    def __init__(self):
        self.deleted = []
        self.inserted = []

    def has_collection(self, collection_name):
        return True

    def delete(self, collection_name, filter):
        self.deleted.append((collection_name, filter))
        return {"delete_count": 2}

    def insert(self, collection_name, data):
        self.inserted.append((collection_name, data))
        return {"ids": [101 + index for index, _ in enumerate(data)]}


def test_build_document_id_is_stable_for_same_source():
    first = build_document_id("obsidian", "my-vault", "Inbox/Python.md")
    second = build_document_id("obsidian", "my-vault", "Inbox/Python.md")

    assert first == second
    assert first.startswith("doc_")


# ==================== AI修改 开始 ====================
# 检索过滤统一处理列表和单个主体，避免状态类型变化导致逐字符过滤。
# ==================== AI修改 结束 ====================
def test_build_item_name_expr_normalizes_filter_values():
    # ==================== AI修改 开始 ====================
    assert build_item_name_expr(["设备A", "设备B"]) == 'item_name in ["设备A", "设备B"]'
    assert build_item_name_expr("设备A") == 'item_name in ["设备A"]'
    assert build_item_name_expr([]) is None
    # ==================== AI修改 结束 ====================


def test_replace_document_deletes_all_old_chunks_before_insert():
    client = FakeMilvusClient()
    store = KnowledgeChunkStore(
        client,
        collection_name="knowledge_chunks",
        ensure_loaded=lambda _: None,
    )
    chunks = [{
        "title": "章节一",
        "content": "正文",
        "part": 1,
        "dense_vector": [0.1, 0.2],
        "sparse_vector": {1: 0.3},
    }]

    result = store.replace_document(
        document_id="doc_001",
        chunks=chunks,
        metadata={
            "source_type": "document",
            "source_id": "manuals",
            "source_path": "设备手册/README.md",
        },
    )

    assert client.deleted == [
        ("knowledge_chunks", "document_id == 'doc_001'")
    ]
    assert client.inserted[0][0] == "knowledge_chunks"
    inserted_chunk = client.inserted[0][1][0]
    assert inserted_chunk["document_id"] == "doc_001"
    assert inserted_chunk["source_type"] == "document"
    assert inserted_chunk["source_id"] == "manuals"
    assert inserted_chunk["source_path"] == "设备手册/README.md"
    assert result["chunks"][0]["id"] == 101


def test_replace_document_escapes_document_id_in_delete_filter():
    client = FakeMilvusClient()
    store = KnowledgeChunkStore(
        client,
        collection_name="knowledge_chunks",
        ensure_loaded=lambda _: None,
    )

    store.replace_document(
        document_id="doc\\special'quote",
        chunks=[{
            "content": "正文",
            "dense_vector": [0.1],
            "sparse_vector": {1: 0.3},
        }],
    )

    assert client.deleted[0][1] == "document_id == 'doc\\\\special\\'quote'"


def test_replace_document_rejects_chunk_without_vector():
    client = FakeMilvusClient()
    store = KnowledgeChunkStore(client, collection_name="knowledge_chunks")

    try:
        store.replace_document(
            document_id="doc_001",
            chunks=[{"content": "正文"}],
        )
    except ValueError as exc:
        assert "dense_vector" in str(exc)
    else:
        raise AssertionError("缺少向量时必须拒绝写入")


def test_delete_source_limits_by_source_id():
    client = FakeMilvusClient()
    store = KnowledgeChunkStore(
        client,
        collection_name="knowledge_chunks",
        ensure_loaded=lambda _: None,
    )

    store.delete_source("obsidian", "vault-a")

    assert client.deleted == [
        (
            "knowledge_chunks",
            "source_type == 'obsidian' and source_id == 'vault-a'",
        )
    ]


def test_delete_path_prefix_can_be_limited_to_one_source_type():
    client = FakeMilvusClient()
    store = KnowledgeChunkStore(
        client,
        collection_name="knowledge_chunks",
        ensure_loaded=lambda _: None,
    )

    store.delete_path_prefix("Inbox/机器学习", source_type="obsidian")

    assert client.deleted == [
        (
            "knowledge_chunks",
            "source_path like 'Inbox/机器学习/%' and source_type == 'obsidian'",
        )
    ]


def test_delete_service_returns_stable_document_summary(monkeypatch):
    class FakeStore:
        def delete_document(self, document_id):
            assert document_id == "doc_001"
            return {"delete_count": 3}

    monkeypatch.setattr(knowledge_service, "KnowledgeChunkStore", FakeStore)

    assert knowledge_service.delete_document_chunks("doc_001") == {
        "document_id": "doc_001",
        "delete_count": 3,
        "acknowledged": True,
    }


# ==================== AI修改 结束 ====================
