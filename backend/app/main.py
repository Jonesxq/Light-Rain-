
"""FastAPI应用主入口模块：应用初始化、路由注册、中间件配置、异常处理"""
import os
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config.settings import settings
from app.core.logger import logger_manager
from app.core.database import db_manager
from app.core.redis import redis_manager

from app.routers.v1 import (
    auth_router,
    user_router,
    chat_router,
    knowledge_router,
    llm_settings_router,
    usage_router,
    news_router
)

# 初始化 LoggerManager
logger_manager.setup()

# 获取当前模块日志器
logger = logger_manager.get_logger(__name__)


# 应用生命周期钩子
async def lifespan(_app: FastAPI):
    """应用生命周期管理：启动时初始化数据库和Redis，关闭时清理资源
    
    Args:
        _app: FastAPI应用实例
    """
    logger.info("🚩 Starting the application...")
    logger.info(f"🚧 You are working in {os.getenv('ENV', 'development')} environment")
    
    try:
        # 初始化数据库连接
        await db_manager.initialize()
        logger.info("🎉 Database connections initialized successfully")
        await db_manager.test_connections()
        logger.info("🎉 Database connections test successfully")
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        logger.warning("⚠️ Application will start without database connections")
    
    try:
        # 初始化 Redis 连接
        await redis_manager.initialize_async()
        logger.info("🎉 Redis connections initialized successfully")
        await redis_manager.async_test_connection()
        logger.info("🎉 Redis connections test successfully")
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        logger.warning("⚠️ Application will start without Redis connections")
    
    yield
    
    # 关闭数据库连接
    try:
        await db_manager.close()
        logger.info("🎉 Database connections closed successfully")
    except Exception as e:
        logger.error(f"❌ Database connection closed failed: {e}")
        logger.warning("⚠️ Database connection closed failed")
    
    # 关闭 Redis 连接
    try:
        await redis_manager.close()
        logger.info("🎉 Redis connections closed successfully")
    except Exception as e:
        logger.error(f"❌ Redis connection closed failed: {e}")
        logger.warning("⚠️ Redis connection closed failed")

# 创建 FastAPI 应用实例
app = FastAPI(
    lifespan=lifespan,
    title=settings.app.APP_NAME,
    version=settings.app.APP_VERSION,
    description=settings.app.APP_DESCRIPTION,
)


# 全局异常处理器
@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    """HTTP异常处理器：统一处理HTTPException并返回JSON格式错误
    
    Args:
        _request: 请求对象
        exc: HTTPException异常对象
        
    Returns:
        JSONResponse: 格式化的错误响应
    """
    logger.error(f"HTTPException: {exc}")
    error_detail = exc.detail
    
    if isinstance(error_detail, dict):
        error_message = error_detail.get("error", str(error_detail))
    else:
        error_message = str(error_detail)
    
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": exc.status_code, "error": error_message},
    )


@app.exception_handler(Exception)
async def general_exception_handler(_request: Request, exc: Exception):
    """通用异常处理器：捕获所有未处理的异常
    
    开发环境返回详细错误信息，生产环境返回通用错误信息
    
    Args:
        _request: 请求对象
        exc: 异常对象
        
    Returns:
        JSONResponse: 格式化的错误响应
    """
    # 打印完整异常堆栈，便于定位问题
    logger.exception(f"Exception: {exc}")
    # 开发环境返回更详细的错误信息
    if os.getenv("ENV", "development") == "development":
        return JSONResponse(
            status_code=500,
            content={"status": 500, "error": str(exc)},
        )
    return JSONResponse(
        status_code=500,
        content={"status": 500, "error": "Internal server error"},
    )

origins = [
    "http://localhost:5173",   # 前端地址（开发时）
    "http://127.0.0.1:5173",
    # 如果你用不同端口或域名，请一并加上
    "http://localhost:4173",  # 静态前端地址
    "http://127.0.0.1:4173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,           # 列表，不要用 "*" 如果 allow_credentials=True
    allow_credentials=True,          # 如果你使用 cookie/session（需要为 true），否则设为 False
    allow_methods=["*"],             # 允许所有方法
    allow_headers=["*"],             # 允许所有请求头
)
# 静态文件挂载
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# 注册路由
app.include_router(auth_router, prefix="/api/v1")
app.include_router(user_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(llm_settings_router, prefix="/api/v1")
app.include_router(usage_router, prefix="/api/v1")
app.include_router(news_router, prefix="/api/v1")


# 健康检查接口
@app.get("/health", tags=["Health"])
async def health_check():
    """健康检查接口：用于监控服务健康状态
    
    Returns:
        dict: 包含健康状态的字典
    """
    return {"status": "healthy"}


# OpenAPI 文档定制
def custom_openapi():
    """自定义OpenAPI文档生成
    
    Returns:
        dict: OpenAPI schema
    """
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=settings.app.APP_NAME,
        version=settings.app.APP_VERSION,
        description=settings.app.APP_DESCRIPTION,
        routes=app.routes,
    )
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


# 本地开发启动入口
if __name__ == "__main__":
    if os.getenv("ENV") == "development":
        logger.info("🚩 Starting the application in development mode...")
        uvicorn.run(
            app="app.main:app",
            host="127.0.0.1",
            port=8000,
            reload=True,
        )

