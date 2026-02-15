"""decorators/rate_limit.py."""
import time
from functools import wraps
from typing import Dict, Callable
from fastapi import HTTPException, Request
from collections import defaultdict


class RateLimiter:
    
    """RateLimiter ??"""
    def __init__(self):
        # Store: {identifier: [(timestamp, count), ...]}
        """__init__ ???"""
        self.requests: Dict[str, list] = defaultdict(list)
    
    def is_allowed(
        self,
        identifier: str,
        max_requests: int,
        window_seconds: int
    ) -> bool:
        """is_allowed ???"""
        current_time = time.time()
        cutoff_time = current_time - window_seconds
        
        # Clean old requests outside the time window
        self.requests[identifier] = [
            req_time for req_time in self.requests[identifier]
            if req_time > cutoff_time
        ]
        
        # Check if limit exceeded
        if len(self.requests[identifier]) >= max_requests:
            return False
        
        # Add current request
        self.requests[identifier].append(current_time)
        return True
    
    def get_remaining(
        self,
        identifier: str,
        max_requests: int,
        window_seconds: int
    ) -> int:
        """get_remaining ???"""
        current_time = time.time()
        cutoff_time = current_time - window_seconds
        
        # Count requests in current window
        recent_requests = [
            req_time for req_time in self.requests[identifier]
            if req_time > cutoff_time
        ]
        
        return max(0, max_requests - len(recent_requests))


# Global rate limiter instance
rate_limiter = RateLimiter()


def rate_limit(
    max_requests: int = 100,
    window_seconds: int = 60,
    identifier_func: Callable[[Request], str] = None
):
    """rate_limit ???"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from args/kwargs
            """wrapper ?????"""
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if not request:
                request = kwargs.get('request')
            
            if not request:
                raise ValueError("Request object not found in function arguments")
            
            # Get identifier (default: client IP)
            if identifier_func:
                identifier = identifier_func(request)
            else:
                identifier = request.client.host if request.client else "unknown"
            
            # Check rate limit
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
            
            # Execute the endpoint
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


# Predefined rate limit decorators for common use cases
def rate_limit_strict(func):
    """rate_limit_strict ???"""
    return rate_limit(max_requests=10, window_seconds=60)(func)


def rate_limit_moderate(func):
    """rate_limit_moderate ???"""
    return rate_limit(max_requests=100, window_seconds=60)(func)


def rate_limit_relaxed(func):
    """rate_limit_relaxed ???"""
    return rate_limit(max_requests=1000, window_seconds=3600)(func)
