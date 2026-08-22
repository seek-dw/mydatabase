# ==================== AI修改 开始 ====================
"""知识切片的批量删除服务。"""

from atguigu.tool.knowledge_chunk_store import KnowledgeChunkStore


def _delete_summary(raw_result) -> dict:
    """把不同 pymilvus 版本的删除返回值整理成稳定的 API 数据。"""
    if isinstance(raw_result, dict):
        delete_count = raw_result.get("delete_count")
    else:
        delete_count = getattr(raw_result, "delete_count", None)
    return {
        "delete_count": delete_count,
        "acknowledged": delete_count is not None,
    }


def delete_document_chunks(document_id: str) -> dict:
    # API 层只返回稳定的 JSON 摘要，不把 pymilvus 的版本相关对象直接暴露给前端。
    result = KnowledgeChunkStore().delete_document(document_id)
    return {
        "document_id": document_id,
        **_delete_summary(result),
    }


def delete_source_chunks(source_type: str, source_id: str | None = None) -> dict:
    result = KnowledgeChunkStore().delete_source(source_type, source_id)
    response = {
        "source_type": source_type,
        **_delete_summary(result),
    }
    if source_id:
        response["source_id"] = source_id
    return response


def delete_directory_chunks(source_path: str, source_type: str | None = None) -> dict:
    result = KnowledgeChunkStore().delete_path_prefix(source_path, source_type)
    response = {
        "source_path": source_path,
        **_delete_summary(result),
    }
    if source_type:
        response["source_type"] = source_type
    return response


# ==================== AI修改 结束 ====================
