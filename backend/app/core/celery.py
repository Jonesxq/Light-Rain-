"""Celery异步任务管理模块 - 提供Celery应用配置和任务管理功能"""
from celery import Celery
from celery.schedules import crontab
from app.core.config.settings import settings
import asyncio
from functools import wraps
from app.core.database.mysql import mysql_manager
from app.core.logger import logger_manager


def with_db_init(func):
    """Celery任务数据库初始化装饰器
    
    用于在Celery任务执行前初始化数据库连接
    
    Args:
        func: 要装饰的Celery任务函数
        
    Returns:
        function: 包装后的函数
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        """包装函数 - 处理数据库初始化和任务执行"""
        logger = logger_manager.get_logger(__name__)
        
        # 初始化数据库连接（Celery worker 需要独立初始化）
        async def init_db():
            """异步初始化数据库连接"""
            try:
                await mysql_manager.initialize()
                logger.debug("Database initialized successfully for Celery task")
            except Exception as e:
                logger.error(f"Failed to initialize database for Celery task: {e}")
                raise
        
        # 在 Celery 任务中执行异步初始化
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # 如果不存在事件循环则创建新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(init_db())
        except Exception as e:
            logger.error(f"Database initialization failed in Celery task: {e}")
            raise
        
        # 执行原始任务
        return func(*args, **kwargs)
    
    return wrapper


class CeleryManager:
    """Celery管理器类 - 管理Celery应用的配置和生命周期"""
    
    def __init__(self):
        """初始化Celery管理器
        
        创建Celery应用实例并配置broker和backend
        """
        self.celery_app = Celery(
            "app",
            broker=settings.celery.CELERY_BROKER_URL,
            backend=settings.celery.CELERY_RESULT_BACKEND,
        )
    
    def setup(self):
        """配置Celery应用参数
        
        设置内容类型、序列化器、时区等配置
        """
        self.celery_app.conf.update(
            broker_connection_retry_on_startup=True,
            accept_content=settings.celery.CELERY_ACCEPT_CONTENT,
            task_serializer=settings.celery.CELERY_TASK_SERIALIZER,
            result_serializer=settings.celery.CELERY_RESULT_SERIALIZER,
            timezone=settings.celery.CELERY_TIMEZONE,
            enable_utc=settings.celery.CELERY_ENABLE_UTC,
        )
    
    def autodiscovery(self):
        """自动发现Celery任务
        
        扫描app.tasks包中的任务模块
        """
        self.celery_app.autodiscover_tasks(
            packages=["app.tasks"],
            force=True,
        )
    
    def start(self):
        """启动Celery应用"""
        self.celery_app.start()
    
    def close(self):
        """关闭Celery应用连接"""
        self.celery_app.close()


# 创建 Celery 应用实例
celery_app = Celery(
    "app",
    broker=settings.celery.CELERY_BROKER_URL,
    backend=settings.celery.CELERY_RESULT_BACKEND,
)

# 配置 Celery 应用
celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    accept_content=settings.celery.CELERY_ACCEPT_CONTENT,
    task_serializer=settings.celery.CELERY_TASK_SERIALIZER,
    result_serializer=settings.celery.CELERY_RESULT_SERIALIZER,
    timezone=settings.celery.CELERY_TIMEZONE,
    enable_utc=settings.celery.CELERY_ENABLE_UTC,
    
    # 优化配置：适配 2GB 内存服务器
    worker_concurrency=1,  # 单 worker 进程，降低内存占用
    worker_prefetch_multiplier=1,  # 避免 worker 预取过多任务
    task_acks_late=True,  # 任务完成后再确认
    worker_max_tasks_per_child=100,  # 每处理 100 个任务重启 worker
    task_time_limit=3600,  # 任务硬超时：1 小时
    task_soft_time_limit=3000,  # 任务软超时：50 分钟

    # 防止重复执行相关配置
    task_reject_on_worker_lost=True,  # worker 崩溃时拒绝任务，避免重复
    task_ignore_result=False,  # 保留任务结果便于追踪

    # 任务执行策略
    task_always_eager=False,  # 保持异步执行
    worker_disable_rate_limits=False,  # 启用限速

    # 结果持久化策略
    task_store_eager_result=True,  # 保存 eager 模式结果
)

# 自动发现任务
# 使用 force=False，避免重复注册任务
celery_app.autodiscover_tasks(
    packages=["app.tasks"],
    force=False,  # 设为 False，避免重复注册
)

# 配置 Celery Beat 周期任务
celery_app.conf.beat_schedule = {
    'backup-database-daily': {
        'task': 'app.tasks.backup_database_task.backup_database_task',
        'schedule': crontab(hour=3, minute=0),  # 每天凌晨 3:00 执行
        'args': (),
        'kwargs': {
            'retention_days': 30,  # 备份保留 30 天
        },
        'options': {
            'expires': 3600,  # 任务过期时间：1 小时
        }
    }
}
