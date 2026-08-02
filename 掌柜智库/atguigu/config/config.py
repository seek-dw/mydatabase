import os
from dotenv import load_dotenv
load_dotenv()

class MinerUConfig:
    """
    MinerU 配置类
    """
    MINERU_API_KEY = os.getenv("MINERU_API_KEY")