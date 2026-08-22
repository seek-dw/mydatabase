# ==================== AI修改 开始 ====================
"""LangGraph 导入节点：把统一切片交给知识存储模块。"""

from atguigu.config.config import MilvusConfig
from atguigu.import_process.base import NodeBase
from atguigu.import_process.state import ImportGraphState
from atguigu.tool.knowledge_chunk_store import (
    KnowledgeChunkStore,
    build_document_id,
)
from atguigu.tool.logger import logger


class NodeImportMilvus(NodeBase):
    """导入流程的薄适配层，不在节点内处理历史 schema 兼容。"""

    name = "node_import_milvus"

    def process(self, state: ImportGraphState):
        chunks = state.get("chunks") or []
        if not chunks:
            logger.error("chunks为空,请检查您的输入")
            raise ValueError("chunks为空,请检查您的输入")

        file_title = state.get("file_title") or chunks[0].get("file_title", "")
        source_type = state.get("source_type") or "document"
        source_id = state.get("source_id") or "local-upload"
        source_path = state.get("source_path") or state.get("local_file_path", "")
        document_id = state.get("document_id") or build_document_id(
            source_type,
            source_id,
            source_path or file_title,
        )

        # ==================== AI修改 开始 ====================
        # 普通、教育和未来新增来源统一使用同一个正文 Collection；
        # 来源差异只通过元数据表达，不再通过 state 切换不同 chunks 表。
        metadata = {
            "document_id": document_id,
            "source_type": source_type,
            "source_id": source_id,
            "source_path": source_path,
            "source_name": state.get("source_name") or file_title,
            "file_hash": state.get("file_hash") or "",
            "file_title": file_title,
        }
        result = KnowledgeChunkStore(
            collection_name=MilvusConfig.milvus_chunks_collection,
        ).replace_document(
            document_id=document_id,
            chunks=chunks,
            metadata=metadata,
        )
        # ==================== AI修改 结束 ====================
        return {
            "chunks": result["chunks"],
            "document_id": document_id,
        }


if __name__ == "__main__":
    logger.info("NodeImportMilvus 需要通过导入图或统一存储接口调用")


# ==================== AI修改 结束 ====================
