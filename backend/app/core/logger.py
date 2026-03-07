"""日志管理模块 - 使用Loguru进行日志记录"""
import sys
import logging
from pathlib import Path
from typing import Optional
from loguru import logger

from app.core.config.settings import settings

class LoggerManager:
    """日志管理器 - 统一管理应用日志输出"""
    def __init__(self):
        """初始化日志管理器"""
        self._initialized = False
        self._loggers = {}
    
    def setup(self) -> None:
        """设置日志输出"""
        if self._initialized:
            return
        
        # 移除默认处理器
        logger.remove()
        
        # 控制台输出
        if settings.logging.LOG_TO_CONSOLE:
            logger.add(
                sys.stdout,
                level=settings.logging.LOG_CONSOLE_LEVEL,
                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                       "<level>{level: <8}</level> | "
                       "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                       "<level>{message}</level>",
                colorize=True,
            )
        
        # 文件输出
        if settings.logging.LOG_TO_FILE:
            log_path = Path(settings.logging.LOG_FILE_PATH)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            logger.add(
                settings.logging.LOG_FILE_PATH,
                level=settings.logging.LOG_LEVEL,
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
                rotation=settings.logging.LOG_ROTATION,
                retention=settings.logging.LOG_RETENTION_PERIOD,
                compression="zip",
                encoding="utf-8",
            )
        
        # 拦截标准库日志
        self._intercept_standard_logging()
        
        self._initialized = True
        logger.info("日志初始化成功")
    
    def _intercept_standard_logging(self) -> None:
        """拦截标准库日志并转发到Loguru"""
        class InterceptHandler(logging.Handler):
            """拦截标准库日志处理器"""
            def emit(self, record: logging.LogRecord) -> None:
                """发送日志记录"""
                # 获取对应的Loguru日志级别
                try:
                    level = logger.level(record.levelname).name
                except ValueError:
                    level = record.levelno
                
                # 找到调用者
                frame, depth = logging.currentframe(), 2
                while frame.f_code.co_filename == logging.__file__:
                    frame = frame.f_back
                    depth += 1
                
                logger.opt(depth=depth, exception=record.exc_info).log(
                    level, record.getMessage()
                )
        
        # 拦截标准库日志
        logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
        
        # 拦截常见库的日志
        for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"]:
            logging.getLogger(logger_name).handlers = [InterceptHandler()]
    
    def get_logger(self, name: Optional[str] = None):
        """获取日志记录器"""
        if not self._initialized:
            self.setup()
        
        if name:
            return logger.bind(name=name)
        return logger


# 创建全局单例
logger_manager = LoggerManager()
