"""
应用配置管理
"""

from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """全局配置"""

    # 应用信息
    APP_NAME: str = "美名集"
    APP_VERSION: str = "0.1.0"
    APP_DESCRIPTION: str = "有据可循的起名工具"

    # 服务配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True

    # 数据文件路径（__file__ = app/core/config.py，需要 .parent.parent.parent 才是项目根）
    BASE_DIR: Path = Path(__file__).parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    DICT_DIR: Path = DATA_DIR / "dict"
    POETRY_DIR: Path = DATA_DIR / "poetry"

    # 字库文件
    CHAR_DB_FILE: str = "chars.json"
    POETRY_DB_FILE: str = "poetry.json"

    # LLM 配置（后续按对比测试结果填入）
    LLM_PROVIDER: str = ""  # deepseek / qwen / zhipu
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    LLM_MODEL: str = ""

    # 起名参数
    MAX_NAME_RESULTS: int = 30  # 单次返回最大名字数
    DEFAULT_NAME_LENGTH: int = 2  # 默认名字字数（不含姓）

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
