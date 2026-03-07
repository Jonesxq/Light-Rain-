
"""核心配置基类模块"""
import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# 从 .env 文件加载环境变量
ENV = os.getenv("ENV", "development")

# 计算项目根目录路径（从 config/base.py 向上 4 级）
ENV_FILE = Path(__file__).resolve().parent.parent.parent.parent / f"secret/.env.{ENV}"

# 尝试加载环境文件，如果不存在则使用系统环境变量
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE, override=True)
else:
    import warnings
    warnings.warn(
        f"环境文件 {ENV_FILE} 不存在。"
        "使用系统环境变量。",
        UserWarning
    )


class EnvBaseSettings(BaseSettings):
    """环境变量基础设置类"""
    class Config:
        """配置类"""
        env_file = ENV_FILE
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "allow"  # 允许模型中未定义的额外字段

