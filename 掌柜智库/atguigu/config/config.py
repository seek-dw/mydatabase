import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(override=True)

# ==================== AI修改 开始 ====================
# 将环境变量安全转换为正整数，避免配置为空或写错时导致服务启动失败。
def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default
# ==================== AI修改 结束 ====================

class MinerUConfig:
    """
    MinerU 配置类
    """
    MINERU_API_KEY = os.getenv("MINERU_API_KEY")

class ModelConfig:
    """
    MODEL_VL_AND_LLM 配置类
    """
    # 重排序模型api -> openrouter
    OPENROUTER_API_KEY= os.getenv("OPENROUTER_API_KEY")
    #视觉模型url
    VL_MODEL_BASE_URL = os.getenv("VL_MODEL_BASE_URL")
    #视觉模型名字
    VL_MODEL_NAME = os.getenv("VL_MODEL_NAME")
    #视觉模型温度
    VL_MODEL_TEMPERATURE = os.getenv("VL_MODEL_TEMPERATURE")
    #语言模型名字
    LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME")
    #语言及视觉模型api
    MODA_API_KEY = os.getenv("MODA_API_KEY")

    # ==================== AI修改 开始 ====================
    # ==================== AI修改 开始 ====================
    # 回答输出预算调整为6144 token：保留详细回答空间，同时避免8192导致模型
    # 在已经回答完整后继续无止境扩写。真正的自然收束还由答案节点的软上限控制。
    # 下面参数均可在根目录 .env 中覆盖，方便不同模型按上下文窗口调节。
    LLM_MAX_TOKENS = _env_int("LLM_MAX_TOKENS", 6144)
    # 普通问题的软收束长度，达到完整句/段落后主动结束，不等到模型硬上限。
    ANSWER_SOFT_MAX_CHARS = _env_int("ANSWER_SOFT_MAX_CHARS", 3600)
    # 明确要求详细/深入/系统讲解的问题允许展开更多，但仍然有合理上限。
    ANSWER_DETAILED_SOFT_MAX_CHARS = _env_int(
        "ANSWER_DETAILED_SOFT_MAX_CHARS", 6000
    )
    # 软上限附近如果还没有完整标点，最多再放宽这部分字符，避免截断半句话。
    ANSWER_SOFT_STOP_GRACE_CHARS = _env_int(
        "ANSWER_SOFT_STOP_GRACE_CHARS", 600
    )
    # ==================== AI修改 结束 ====================
    # 历史消息从10条扩大到20条，约保留10轮问答，减少多轮对话遗忘。
    QUERY_HISTORY_LIMIT = _env_int("QUERY_HISTORY_LIMIT", 20)
    # 检索上下文预算从10000字符扩大到18000字符，给详细回答更多依据。
    ANSWER_MAX_CONTEXT_CHARS = _env_int("ANSWER_MAX_CONTEXT_CHARS", 18000)
    # 历史文本设置独立上限，避免记忆扩大后挤占当前问题和回答输出空间。
    ANSWER_MAX_HISTORY_CHARS = _env_int("ANSWER_MAX_HISTORY_CHARS", 16000)
    # 前端上下文进度条的展示上限，与实际模型输出预算分开控制。
    ANSWER_CONTEXT_DISPLAY_LIMIT = _env_int("ANSWER_CONTEXT_DISPLAY_LIMIT", 40000)
    # 模型总上下文窗口；输出预算、提示词安全余量会从这里扣除后再分配资料。
    LLM_CONTEXT_WINDOW_TOKENS = _env_int("LLM_CONTEXT_WINDOW_TOKENS", 32768)
    # 给系统提示词、格式开销和token估算误差预留的安全空间。
    LLM_PROMPT_SAFETY_TOKENS = _env_int("LLM_PROMPT_SAFETY_TOKENS", 2048)
    # ==================== AI修改 结束 ====================

class MinioConfig:
    """
    MINIO配置类
    """

    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
    # 访问密钥
    MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
    # 私有密钥
    MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
    # 存储桶名称
    MINIO_BUCKET_NAME = os.getenv("MINIO_BUCKET_NAME")
    # 图片上传目录
    MINIO_IMG_DIR = os.getenv("MINIO_IMG_DIR")

class EmbeddingConfig:
    """
    EMBEDDING_MODEL配置类
    """

    # 嵌入模型
    EMBEDDING_MODEL =  os.getenv("EMBEDDING_MODEL")
    # 向量化设备
    DEVICE = os.getenv("DEVICE")
    # 精度训练 这读出来是字符串,所以一定要判断然后变成布尔
    USE_FP16 = True if os.getenv("USE_FP16") in ["True"] else False

class MilvusConfig:
    """
    MILVUS配置类
    """
    #创建客户端url地址
    milvus_url = os.getenv("MILVUS_URL")
    #主体识别集合表
    milvus_item_collection = os.getenv("ITEM_COLLECTION")
    #chunks集合表
    milvus_chunks_collection = os.getenv("CHUNKS_COLLECTION")
    # ==================== AI修改 开始 ====================
    # 教育数据单独使用一张新表，避免旧 chunks_db schema 没有教育字段时影响普通文档。
    # 未配置时自动使用“普通表名_education”，首次教育导入会自动创建。
    education_chunks_collection = os.getenv(
        "EDUCATION_CHUNKS_COLLECTION",
        f"{milvus_chunks_collection}_education",
    )
    # ==================== AI修改 结束 ====================

class MongoConfig:
    """
    Mongo配置类
    """

    # mongo的链接地址
    mongo_url = os.getenv("MONGO_URL")
    # 数据库名
    mongo_db_name = os.getenv("MONGO_DB_NAME")

class McpConfig:
    """
    Mcp配置类
    """

    # mcp连接地址
    mcp_server = os.getenv("MCP_SERVER")
    mcp_api_key = os.getenv("OPENAI_API_KEY")
