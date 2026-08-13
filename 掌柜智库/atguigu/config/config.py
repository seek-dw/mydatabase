import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(override=True)

class MinerUConfig:
    """
    MinerU 配置类
    """
    MINERU_API_KEY = os.getenv("MINERU_API_KEY")

class ModelConfig:
    """
    MODEL_VL_AND_LLM 配置类
    """
    #视觉模型api
    VL_MODEL_API_KEY = os.getenv("VL_MODEL_API_KEY")
    #视觉模型url
    VL_MODEL_BASE_URL = os.getenv("VL_MODEL_BASE_URL")
    #视觉模型名字
    VL_MODEL_NAME = os.getenv("VL_MODEL_NAME")
    #视觉模型温度
    VL_MODEL_TEMPERATURE = os.getenv("VL_MODEL_TEMPERATURE")
    #语言模型名字
    LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME")

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
