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
        
        # Initialize database connection (Celery worker needs separate initialization)
        async def init_db():
            """异步初始化数据库连接"""
            try:
                await mysql_manager.initialize()
                logger.debug("Database initialized successfully for Celery task")
            except Exception as e:
                logger.error(f"Failed to initialize database for Celery task: {e}")
                raise
        
        # Run async initialization in Celery task
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # If no event loop exists, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(init_db())
        except Exception as e:
            logger.error(f"Database initialization failed in Celery task: {e}")
            raise
        
        # Execute original task
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


# Create a celery app instance
celery_app = Celery(
    "app",
    broker=settings.celery.CELERY_BROKER_URL,
    backend=settings.celery.CELERY_RESULT_BACKEND,
)

# Configure the celery app
celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    accept_content=settings.celery.CELERY_ACCEPT_CONTENT,
    task_serializer=settings.celery.CELERY_TASK_SERIALIZER,
    result_serializer=settings.celery.CELERY_RESULT_SERIALIZER,
    timezone=settings.celery.CELERY_TIMEZONE,
    enable_utc=settings.celery.CELERY_ENABLE_UTC,
    
    # Optimization configuration: suitable for 2GB memory server
    worker_concurrency=1,  # 1 worker process (save memory)
    worker_prefetch_multiplier=1,  # Avoid worker prefetching too many tasks
    task_acks_late=True,  # Acknowledge task after completion
    worker_max_tasks_per_child=100,  # Restart worker after processing 100 tasks
    task_time_limit=3600,  # Task timeout: 1 hour
    task_soft_time_limit=3000,  # Soft timeout: 50 minutes
    
    # Configuration to prevent duplicate task execution
    task_reject_on_worker_lost=True,  # Reject tasks when worker crashes to avoid duplicates
    task_ignore_result=False,  # Save task results for tracking
    
    # Ensure tasks execute only once
    task_always_eager=False,  # Ensure tasks execute asynchronously
    worker_disable_rate_limits=False,  # Enable rate limiting
    
    # Use unique identifiers to prevent duplicates
    task_store_eager_result=True,  # Store eager mode results
)

# Auto-discover tasks
# Remove force=True to avoid duplicate task registration
celery_app.autodiscover_tasks(
    packages=["app.tasks"],
    force=False,  # Set to False to avoid duplicate task registration
)

# Configure Celery Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    'backup-database-daily': {
        'task': 'app.tasks.backup_database_task.backup_database_task',
        'schedule': crontab(hour=3, minute=0),  # Execute daily at 3:00 AM
        'args': (),
        'kwargs': {
            'retention_days': 30,  # Keep backups for 30 days
        },
        'options': {
            'expires': 3600,  # Task expiration time: 1 hour
        }
    }
}
