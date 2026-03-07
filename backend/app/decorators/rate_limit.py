"""请求限流模块 - 提供API请求频率限制功能"""
import time
from functools import wraps
from typing import Dict, Callable
from fastapi import HTTPException, Request
from collections import defaultdict


class RateLimiter:
    """请求限流器 - 基于时间窗口的限流算法实现"""
    
    def __init__(self):
        """初始化请求限流器
        
        数据结构: {identifier: [timestamp1, timestamp2, ...]}
        """
        self.requests: Dict[str, list] = defaultdict(list)
    
    def is_allowed(
        self,
        identifier: str,
        max_requests: int,
        window_seconds: int
    ) -> bool:
        """检查请求是否允许通过
        
        Args:
            identifier: 请求标识符（如客户端IP、用户ID等）
            max_requests: 时间窗口内最大请求数
            window_seconds: 时间窗口长度（秒）
            
        Returns:
            bool: 请求允许返回True，限流返回False
        """
        current_time = time.time()
        cutoff_time = current_time - window_seconds
        
        # 清理时间窗口外的旧请求记录
        self.requests[identifier] = [
            req_time for req_time in self.requests[identifier]
            if req_time > cutoff_time
        ]
        
        # 检查是否超过限流阈值
        if len(self.requests[identifier]) >= max_requests:
            return False
        
        # 记录当前请求
        self.requests[identifier].append(current_time)
        return True
    
    def get_remaining(
        self,
        identifier: str,
        max_requests: int,
        window_seconds: int
    ) -> int:
        """获取剩余请求次数
        
        Args:
            identifier: 请求标识符
            max_requests: 时间窗口内最大请求数
            window_seconds: 时间窗口长度（秒）
            
        Returns:
            int: 剩余请求次数
        """
        current_time = time.time()
        cutoff_time = current_time - window_seconds
        
        # 统计当前时间窗口内的请求数
        recent_requests = [
            req_time for req_time in self.requests[identifier]
            if req_time > cutoff_time
        ]
        
        return max(0, max_requests - len(recent_requests))


# 全局限流器实例
rate_limiter = RateLimiter()


def rate_limit(
    max_requests: int = 100,
    window_seconds: int = 60,
    identifier_func: Callable[[Request], str] = None
):
    """请求限流装饰器
    
    Args:
        max_requests: 时间窗口内最大请求数，默认100
        window_seconds: 时间窗口长度（秒），默认60
        identifier_func: 自定义标识符生成函数，默认为客户端IP
        
    Returns:
        Callable: 装饰器函数
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            """限流装饰器内部包装函数"""
            # 从参数中提取请求对象
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if not request:
                request = kwargs.get('request')
            
            if not request:
                raise ValueError("Request object not found in function arguments")
            
            # 获取请求标识符（默认使用客户端IP）
            if identifier_func:
                identifier = identifier_func(request)
            else:
                identifier = request.client.host if request.client else "unknown"
            
            # 检查是否限流
            if not rate_limiter.is_allowed(identifier, max_requests, window_seconds):
                remaining = rate_limiter.get_remaining(identifier, max_requests, window_seconds)
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Try again in {window_seconds} seconds.",
                    headers={
                        "X-RateLimit-Limit": str(max_requests),
                        "X-RateLimit-Remaining": str(remaining),
                        "X-RateLimit-Reset": str(int(time.time() + window_seconds))
                    }
                )
            
            # 执行端点函数
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


# 预定义的常用限流装饰器
def rate_limit_strict(func):
    """严格限流装饰器 - 每分钟最多10次请求
    
    Args:
        func: 被装饰的函数
        
    Returns:
        Callable: 装饰后的函数
    """
    return rate_limit(max_requests=10, window_seconds=60)(func)


def rate_limit_moderate(func):
    """中等限流装饰器 - 每分钟最多100次请求
    
    Args:
        func: 被装饰的函数
        
    Returns:
        Callable: 装饰后的函数
    """
    return rate_limit(max_requests=100, window_seconds=60)(func)


def rate_limit_relaxed(func):
    """宽松限流装饰器 - 每小时最多1000次请求
    
    Args:
        func: 被装饰的函数
        
    Returns:
        Callable: 装饰后的函数
    """
    return rate_limit(max_requests=1000, window_seconds=3600)(func)
