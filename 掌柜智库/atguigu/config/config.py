import os
from dotenv import load_dotenv
load_dotenv(override=True)

class MinerUConfig:
    """
    MinerU 配置类
    """
    MINERU_API_KEY = os.getenv("MINERU_API_KEY")

class ModelConfig:
    """
    QWEN3ALL 配置类
    """
    qwen3vl_api_key = os.getenv("QWEN3VL_API_KEY")
    qwen3vl_base_url = os.getenv("QWEN3VL_BASE_URL")
    qwen3vl_model_name = os.getenv("VL_DEFULT_MODEL")
    qwen3vl_model_temperature = os.getenv("LLM_DEFULT_TEMPERATURE")
    qwen3_flash_model = os.getenv("QWEN3_FLASH_MODEL")