"""FastAPI application main entry point"""

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
    llm_settings_router
)

# Create LoggerManager instance
logger_manager.setup()

# Create Logger instance
logger = logger_manager.get_logger(__name__)


# Create lifespan
async def lifespan(_app: FastAPI):
    """Application lifespan management"""
    logger.info("🚩 Starting the application...")
    logger.info(f"🚧 You are working in {os.getenv('ENV', 'development')} environment")
    
    try:
        # Initialize database connection
        await db_manager.initialize()
        logger.info("🎉 Database connections initialized successfully")
        await db_manager.test_connections()
        logger.info("🎉 Database connections test successfully")
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        logger.warning("⚠️ Application will start without database connections")
    
    try:
        # Initialize Redis connection
        await redis_manager.initialize_async()
        logger.info("🎉 Redis connections initialized successfully")
        await redis_manager.async_test_connection()
        logger.info("🎉 Redis connections test successfully")
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        logger.warning("⚠️ Application will start without Redis connections")
    
    yield
    
    # Close database connection
    try:
        await db_manager.close()
        logger.info("🎉 Database connections closed successfully")
    except Exception as e:
        logger.error(f"❌ Database connection closed failed: {e}")
        logger.warning("⚠️ Database connection closed failed")
    
    # Close Redis connections
    try:
        await redis_manager.close()
        logger.info("🎉 Redis connections closed successfully")
    except Exception as e:
        logger.error(f"❌ Redis connection closed failed: {e}")
        logger.warning("⚠️ Redis connection closed failed")

# Create FastAPI instance
app = FastAPI(
    lifespan=lifespan,
    title=settings.app.APP_NAME,
    version=settings.app.APP_VERSION,
    description=settings.app.APP_DESCRIPTION,
)


# Global exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    """HTTP exception handler"""
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
    """General exception handler"""
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
# # CORS middleware
# allow_origins = [x.strip() for x in settings.cors.CORS_ALLOWED_ORIGINS.split(',') if x.strip()]
# allow_methods = [x.strip() for x in settings.cors.CORS_ALLOW_METHODS.split(',') if x.strip()]
# allow_headers = [x.strip() for x in settings.cors.CORS_ALLOW_HEADERS.split(',') if x.strip()]
# allow_credentials = settings.cors.CORS_ALLOW_CREDENTIALS
# expose_headers = [x.strip() for x in settings.cors.CORS_EXPOSE_HEADERS.split(',') if x.strip()]
#
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=allow_origins,
#     allow_methods=allow_methods,
#     allow_headers=allow_headers,
#     allow_credentials=allow_credentials,
#     expose_headers=expose_headers,
# )


# Static files
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# Include routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(user_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(llm_settings_router, prefix="/api/v1")


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


# OpenAPI documentation
def custom_openapi():
    """Custom OpenAPI documentation"""
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


# Start application
if __name__ == "__main__":
    if os.getenv("ENV") == "development":
        logger.info("🚩 Starting the application in development mode...")
        uvicorn.run(
            app="app.main:app",
            host="127.0.0.1",
            port=8000,
            reload=True,
        )
