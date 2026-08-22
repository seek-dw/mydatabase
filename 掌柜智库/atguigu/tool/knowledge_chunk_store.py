# ==================== AI修改 开始 ====================
"""统一知识切片的 Milvus 持久化模块。

运行时只面向新的统一 schema。旧集合如果没有这些字段，应在重新导入前删除，
而不是把历史 schema 兼容逻辑继续带入正常导入流程。
"""

from __future__ import annotations

import hashlib
# ==================== AI修改 开始 ====================
from pathlib import Path
# ==================== AI修改 结束 ====================
from typing import Any, Callable, Mapping

from pymilvus import DataType

from atguigu.config.config import MilvusConfig
from atguigu.tool.logger import logger
from atguigu.tool.milvus_client_create import (
    ensure_collection_loaded,
    get_milvus_client,
)


# ==================== AI修改 开始 ====================
# 只有这些通用字段和教育查询仍需使用的字段会写入 Milvus；来源专属扩展字段
# 不应该继续污染统一 schema，后续可放到文档目录中。
KNOWLEDGE_CHUNK_FIELDS = (
    "document_id",
    "source_type",
    "source_id",
    "source_path",
    "source_name",
    "file_hash",
    "file_title",
    "title",
    "content",
    "item_name",
    "part",
    "dense_vector",
    "sparse_vector",
    # 教育字段保留在统一 schema 中，避免现有课程目录接口失效。
    "content_type",
    "code",
    "q_type",
    "course_name",
    "course_code",
    "chapter_name",
    "course_category",
    "target_users",
    "learning_goals",
    "project_name",
    "question_bank_name",
    "question_bank_code",
    "question_code",
    "question_type",
)
# ==================== AI修改 结束 ====================

# ==================== AI修改 开始 ====================
# Milvus 的 VARCHAR 超长时会直接拒绝插入。这里做校验而不是截断正文，
# 避免为了满足 schema 悄悄丢掉回答依据。
_STRING_LIMITS = {
    "document_id": 128,
    "source_type": 64,
    "source_id": 500,
    "source_path": 2000,
    "source_name": 500,
    "file_hash": 128,
    "file_title": 500,
    "title": 1000,
    "content": 5000,
    "item_name": 200,
    "content_type": 64,
    "code": 200,
    "q_type": 64,
    "course_name": 500,
    "course_code": 200,
    "chapter_name": 1000,
    "course_category": 200,
    "target_users": 500,
    "learning_goals": 500,
    "project_name": 500,
    "question_bank_name": 500,
    "question_bank_code": 200,
    "question_code": 200,
    "question_type": 64,
}
# ==================== AI修改 结束 ====================

# ==================== AI修改 开始 ====================
# 普通文档不会携带教育字段，因此由统一入库层补空值，保证所有来源使用同一行结构。
_DEFAULTS: dict[str, Any] = {
    "source_type": "document",
    "source_id": "",
    "source_path": "",
    "source_name": "",
    "file_hash": "",
    "file_title": "",
    "title": "",
    "content": "",
    "item_name": "",
    "part": 0,
    "content_type": "doc",
    "code": "",
    "q_type": "",
    "course_name": "",
    "course_code": "",
    "chapter_name": "",
    "course_category": "",
    "target_users": "",
    "learning_goals": "",
    "project_name": "",
    "question_bank_name": "",
    "question_bank_code": "",
    "question_code": "",
    "question_type": "",
}
# ==================== AI修改 结束 ====================


def build_document_id(source_type: str, source_id: str, source_path: str) -> str:
    """根据来源和路径生成稳定的文档 ID。"""
    # source_type + source_id + source_path 共同构成文档身份；不能只用 file_title，
    # 因为不同目录中可以存在同名文件。
    identity = "\x1f".join(
        str(value or "").strip().replace("\\", "/")
        for value in (source_type, source_id, source_path)
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
    return f"doc_{digest}"


# ==================== AI修改 开始 ====================
def build_local_source_identity(source_root: str | Path, source_file: str | Path) -> tuple[str, str]:
    """把本地原始目录和文件转换为稳定的来源 ID 与相对路径。"""
    root = Path(source_root).expanduser().resolve()
    file_path = Path(source_file).expanduser().resolve()
    try:
        relative_path = file_path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"文件不在来源目录内: {file_path}") from exc
    # source_id 标识整个来源目录，source_path 只标识目录内的相对文件。
    return root.as_posix(), relative_path.as_posix()


def build_upload_source_identity(filename: str | None) -> tuple[str, str]:
    """把浏览器上传文件转换为不包含随机任务目录的稳定身份。"""
    normalized = str(filename or "").replace("\\", "/")
    safe_filename = normalized.rsplit("/", 1)[-1].strip()
    if not safe_filename or safe_filename in {".", ".."}:
        raise ValueError("上传文件名不能为空")
    # 浏览器上传没有原始目录，固定来源类型并用文件名做文档级替换键。
    return "browser-upload", safe_filename


# ==================== AI修改 结束 ====================


def escape_milvus_string(value: str) -> str:
    """转义 Milvus filter 字符串中的反斜杠和引号。"""
    return str(value or "").replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')


class KnowledgeChunkStore:
    """统一知识切片的写入和批量删除接口。"""

    def __init__(
        self,
        client=None,
        collection_name: str | None = None,
        ensure_loaded: Callable[[str], None] | None = None,
    ):
        self.client = client or get_milvus_client()
        self.collection_name = collection_name or MilvusConfig.milvus_chunks_collection
        self._ensure_loaded = ensure_loaded or ensure_collection_loaded

    def ensure_collection(self, dim: int) -> None:
        # 统一表只在第一次导入时创建；后续导入复用同一个 schema 和索引。
        if not self.client.has_collection(collection_name=self.collection_name):
            schema = _build_schema_for_client(self.client, dim)
            index_params = self.client.prepare_index_params()
            index_params.add_index(
                field_name="dense_vector",
                index_type="IVF_FLAT",
                metric_type="COSINE",
                params={"nlist": 120, "nprobe": 12},
            )
            index_params.add_index(
                field_name="sparse_vector",
                index_type="SPARSE_INVERTED_INDEX",
                metric_type="IP",
                params={
                    "inverted_index_algo": "DAAT_MAXSCORE",
                    "NORMALIZE": True,
                    "quantization": "none",
                },
            )
            self.client.create_collection(
                collection_name=self.collection_name,
                schema=schema,
                index_params=index_params,
            )
            logger.info(f"统一知识切片集合创建完成: {self.collection_name}")
        # 删除和查询都要求 Collection 已加载，统一在存储层保证这个前置条件。
        self._ensure_loaded(self.collection_name)

    def replace_document(
        self,
        document_id: str,
        chunks: list[Mapping[str, Any]],
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not str(document_id or "").strip():
            raise ValueError("document_id不能为空")
        if not chunks:
            raise ValueError("chunks不能为空")

        metadata = dict(metadata or {})
        prepared_chunks = []
        for chunk in chunks:
            # 先验证向量，再合并文档元数据；这样失败时不会先删除旧文档。
            if not chunk.get("dense_vector"):
                raise ValueError("chunk缺少dense_vector")
            if not chunk.get("sparse_vector"):
                raise ValueError("chunk缺少sparse_vector")

            prepared = dict(_DEFAULTS)
            prepared.update(dict(chunk))
            prepared.update(
                {
                    key: value
                    for key, value in metadata.items()
                    if value is not None
                }
            )
            prepared["document_id"] = document_id
            prepared["source_name"] = prepared.get("source_name") or prepared.get("file_title", "")
            self._validate_chunk(prepared)
            # 只选取新 schema 认识的字段，避免来源适配器携带临时字段导致插入失败。
            prepared_chunks.append(
                {
                    field: prepared.get(field, _DEFAULTS.get(field))
                    for field in KNOWLEDGE_CHUNK_FIELDS
                    if field != "source_name" or field in prepared
                }
            )

        dim = len(prepared_chunks[0]["dense_vector"])
        self.ensure_collection(dim)
        # 只有整篇新文档已经完成校验并准备好后，才删除同 document_id 的旧切片。
        # 这保证向量化或字段校验失败时，旧版本不会先被清空。
        self.client.delete(
            collection_name=self.collection_name,
            filter=f"document_id == '{escape_milvus_string(document_id)}'",
        )
        result = self.client.insert(
            collection_name=self.collection_name,
            data=prepared_chunks,
        )
        ids = result.get("ids") or []
        # Milvus 返回 ID 数量异常意味着写入结果不能和 chunk 一一对应，必须显式失败。
        if len(ids) != len(prepared_chunks):
            raise RuntimeError(
                f"Milvus返回ID数量异常: expected={len(prepared_chunks)}, actual={len(ids)}"
            )

        result_chunks = []
        for original, prepared, chunk_id in zip(chunks, prepared_chunks, ids):
            enriched = dict(original)
            enriched.update(
                {
                    key: value
                    for key, value in prepared.items()
                    if key not in {"dense_vector", "sparse_vector"}
                }
            )
            enriched["id"] = chunk_id
            result_chunks.append(enriched)
        return {"chunks": result_chunks, "ids": ids}

    def delete_document(self, document_id: str):
        if not str(document_id or "").strip():
            raise ValueError("document_id不能为空")
        self._ensure_loaded(self.collection_name)
        # 一篇文档的全部切片共用 document_id，因此一次 filter 可以完成整篇删除。
        return self.client.delete(
            collection_name=self.collection_name,
            filter=f"document_id == '{escape_milvus_string(document_id)}'",
        )

    def delete_source(self, source_type: str, source_id: str | None = None):
        if not str(source_type or "").strip():
            raise ValueError("source_type不能为空")
        # source_id 可选：传入时删除某个 Vault/项目，不传时删除整个来源类型。
        conditions = [f"source_type == '{escape_milvus_string(source_type)}'"]
        if source_id:
            conditions.append(f"source_id == '{escape_milvus_string(source_id)}'")
        return self._delete_by_filter(" and ".join(conditions))

    def delete_path_prefix(self, source_path: str, source_type: str | None = None):
        prefix = str(source_path or "").strip().replace("\\", "/").rstrip("/")
        if not prefix:
            raise ValueError("source_path不能为空")
        # 用目录前缀批量命中目录下所有文档，避免用户逐个寻找文件切片。
        conditions = [f"source_path like '{escape_milvus_string(prefix)}/%'"]
        if source_type:
            conditions.append(f"source_type == '{escape_milvus_string(source_type)}'")
        return self._delete_by_filter(" and ".join(conditions))

    def _delete_by_filter(self, filter_expression: str):
        self._ensure_loaded(self.collection_name)
        return self.client.delete(
            collection_name=self.collection_name,
            filter=filter_expression,
        )

    @staticmethod
    def _validate_chunk(chunk: Mapping[str, Any]) -> None:
        for field, max_length in _STRING_LIMITS.items():
            value = chunk.get(field, "")
            if not isinstance(value, str):
                continue
            if len(value) > max_length:
                raise ValueError(
                    f"{field}超过统一 schema 限制: {len(value)} > {max_length}；"
                    "请在切片或来源解析阶段处理，不在入库层静默截断"
                )


def _build_schema_for_client(client, dim: int):
    """使用传入客户端建 schema，便于测试和多客户端场景复用。"""
    schema = client.create_schema(auto_id=True)
    schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
    schema.add_field(field_name="document_id", datatype=DataType.VARCHAR, max_length=128)
    schema.add_field(field_name="source_type", datatype=DataType.VARCHAR, max_length=64)
    schema.add_field(field_name="source_id", datatype=DataType.VARCHAR, max_length=500)
    schema.add_field(field_name="source_path", datatype=DataType.VARCHAR, max_length=2000)
    schema.add_field(field_name="source_name", datatype=DataType.VARCHAR, max_length=500)
    schema.add_field(field_name="file_hash", datatype=DataType.VARCHAR, max_length=128)
    schema.add_field(field_name="file_title", datatype=DataType.VARCHAR, max_length=500)
    schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=1000)
    schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=5000)
    schema.add_field(field_name="item_name", datatype=DataType.VARCHAR, max_length=200)
    schema.add_field(field_name="part", datatype=DataType.INT64)
    schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=dim)
    schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)
    schema.add_field(field_name="content_type", datatype=DataType.VARCHAR, max_length=64)
    schema.add_field(field_name="code", datatype=DataType.VARCHAR, max_length=200)
    schema.add_field(field_name="q_type", datatype=DataType.VARCHAR, max_length=64)
    schema.add_field(field_name="course_name", datatype=DataType.VARCHAR, max_length=500)
    schema.add_field(field_name="course_code", datatype=DataType.VARCHAR, max_length=200)
    schema.add_field(field_name="chapter_name", datatype=DataType.VARCHAR, max_length=1000)
    schema.add_field(field_name="course_category", datatype=DataType.VARCHAR, max_length=200)
    schema.add_field(field_name="target_users", datatype=DataType.VARCHAR, max_length=500)
    schema.add_field(field_name="learning_goals", datatype=DataType.VARCHAR, max_length=500)
    schema.add_field(field_name="project_name", datatype=DataType.VARCHAR, max_length=500)
    schema.add_field(field_name="question_bank_name", datatype=DataType.VARCHAR, max_length=500)
    schema.add_field(field_name="question_bank_code", datatype=DataType.VARCHAR, max_length=200)
    schema.add_field(field_name="question_code", datatype=DataType.VARCHAR, max_length=200)
    schema.add_field(field_name="question_type", datatype=DataType.VARCHAR, max_length=64)
    return schema


# ==================== AI修改 结束 ====================
