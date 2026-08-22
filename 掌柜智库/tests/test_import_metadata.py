# ==================== AI修改 开始 ====================
"""导入入口生成统一文档元数据的测试。"""

from atguigu.import_process.nodes import node_import_milvus
from atguigu.import_process.nodes.node_entry import NodeEntry
from atguigu.tool.knowledge_chunk_store import (
    build_local_source_identity,
    build_upload_source_identity,
)


def test_node_entry_generates_stable_document_metadata(tmp_path):
    source = tmp_path / "Python基础.md"
    source.write_text("# Python", encoding="utf-8")
    node = NodeEntry()

    first = node({"local_file_path": str(source)})
    second = node({"local_file_path": str(source)})

    assert first["source_type"] == "document"
    assert first["source_id"] == "local-upload"
    assert first["source_path"] == str(source)
    assert first["document_id"] == second["document_id"]


def test_node_entry_preserves_explicit_source_identity(tmp_path):
    source = tmp_path / "note.md"
    source.write_text("# Note", encoding="utf-8")

    result = NodeEntry()({
        "local_file_path": str(source),
        "source_type": "obsidian",
        "source_id": "vault-a",
        "source_path": "Inbox/note.md",
        "document_id": "doc_explicit",
    })

    assert result["source_type"] == "obsidian"
    assert result["source_id"] == "vault-a"
    assert result["source_path"] == "Inbox/note.md"
    assert result["document_id"] == "doc_explicit"


# ==================== AI修改 开始 ====================
def test_local_source_identity_uses_original_relative_path_not_staging_path(tmp_path):
    source_root = tmp_path / "资料"
    source_file = source_root / "课程" / "Python.md"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("# Python", encoding="utf-8")

    first = build_local_source_identity(source_root, source_file)
    second = build_local_source_identity(source_root, source_file)

    assert first == second
    assert first[0] == source_root.resolve().as_posix()
    assert first[1] == "课程/Python.md"


def test_upload_source_identity_uses_filename_not_random_task_directory():
    first = build_upload_source_identity(r"old-task\Python.md")
    second = build_upload_source_identity(r"new-task\Python.md")

    assert first == ("browser-upload", "Python.md")
    assert second == first


def test_run_graph_passes_source_identity_to_import_graph(monkeypatch):
    from atguigu.web.api import app_service

    captured = {}

    def fake_create_runner(init_state):
        captured.update(init_state)

    monkeypatch.setattr(app_service.ImportGraphRunner, "create_runner", fake_create_runner)
    monkeypatch.setattr(app_service, "update_task_status", lambda *args, **kwargs: None)

    app_service.run_graph(
        "task-1",
        r"E:\runtime\random-task\Python.md",
        r"E:\runtime\random-task",
        "document",
        r"E:\资料\课程",
        "课程/Python.md",
    )

    assert captured["source_id"] == r"E:\资料\课程"
    assert captured["source_path"] == "课程/Python.md"


# ==================== AI修改 结束 ====================


def test_import_node_returns_only_declared_graph_state(monkeypatch):
    class FakeStore:
        def __init__(self, **kwargs):
            pass

        def replace_document(self, **kwargs):
            return {
                "chunks": [{"id": 7, "content": "正文"}],
                "ids": [7],
            }

    monkeypatch.setattr(node_import_milvus, "KnowledgeChunkStore", FakeStore)

    result = node_import_milvus.NodeImportMilvus()({
        "document_id": "doc_001",
        "source_type": "document",
        "source_id": "manuals",
        "source_path": "manual.md",
        "file_title": "manual",
        "chunks": [{"content": "正文"}],
    })

    assert result == {
        "chunks": [{"id": 7, "content": "正文"}],
        "document_id": "doc_001",
    }


# ==================== AI修改 结束 ====================
