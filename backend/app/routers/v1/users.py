"""用户路由模块 - 提供用户信息管理API"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.core.deps import get_current_user, get_current_superuser
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdate
from app.crud.user import user_crud

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """获取当前登录用户的信息
    
    Args:
        current_user: 当前登录用户
        
    Returns:
        UserResponse: 用户信息
    """
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """更新当前登录用户的信息
    
    支持更新用户名、邮箱、密码和启用状态，修改用户名或邮箱时会校验唯一性
    
    Args:
        user_update: 用户更新信息
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        UserResponse: 更新后的用户信息
        
    Raises:
        HTTPException: 用户名或邮箱已存在时返回400错误
    """
    # 如修改用户名，需要校验唯一性
    if user_update.username and user_update.username != current_user.username:
        existing_user = await user_crud.get_by_username(db, user_update.username)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )
    
    # 如修改邮箱，需要校验唯一性
    if user_update.email and user_update.email != current_user.email:
        existing_user = await user_crud.get_by_email(db, user_update.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
    
    updated_user = await user_crud.update(db, current_user.id, user_update)
    
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return updated_user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_current_user(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """删除当前登录用户账户
    
    Args:
        current_user: 当前登录用户
        db: 数据库会话
        
    Raises:
        HTTPException: 用户不存在时返回404错误
    """
    success = await user_crud.delete(db, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )


# ========== 管理员操作 ==========

@router.get("/", response_model=List[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db)
):
    """获取用户列表（管理员权限）
    
    Args:
        skip: 跳过的记录数
        limit: 返回的最大记录数
        current_user: 当前登录的超级管理员
        db: 数据库会话
        
    Returns:
        List[UserResponse]: 用户列表
    """
    users = await user_crud.get_all(db, skip=skip, limit=limit)
    return users


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db)
):
    """获取指定用户信息（管理员权限）
    
    Args:
        user_id: 用户ID
        current_user: 当前登录的超级管理员
        db: 数据库会话
        
    Returns:
        UserResponse: 用户信息
        
    Raises:
        HTTPException: 用户不存在时返回404错误
    """
    user = await user_crud.get_by_id(db, user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db)
):
    """更新指定用户信息（管理员权限）
    
    Args:
        user_id: 用户ID
        user_update: 用户更新信息
        current_user: 当前登录的超级管理员
        db: 数据库会话
        
    Returns:
        UserResponse: 更新后的用户信息
        
    Raises:
        HTTPException: 用户不存在时返回404错误
    """
    updated_user = await user_crud.update(db, user_id, user_update)
    
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return updated_user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db)
):
    """删除指定用户（管理员权限）
    
    防止管理员误删自己的账户
    
    Args:
        user_id: 用户ID
        current_user: 当前登录的超级管理员
        db: 数据库会话
        
    Raises:
        HTTPException: 尝试删除自己时返回400错误，用户不存在时返回404错误
    """
    # 防止管理员误删自己
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself"
        )
    
    success = await user_crud.delete(db, user_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
