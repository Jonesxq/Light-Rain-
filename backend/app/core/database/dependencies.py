"""FastAPI dependenciesinjection"""

from fastapi import Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select
from fastapi.security import APIKeyCookie
from app.core.database.mysql import mysql_manager
from app.core.logger import logger_manager
from app.crud.auth_crud import get_auth_crud
from app.models.auth_model import Token, TokenType
from app.core.security import security_manager
from app.core.config.settings import settings

get_access_token_cookie = APIKeyCookie(
    name="access_token",
    auto_error=False,
    scheme_name="Bearer",
    description="Access token for authentication",
)

get_refresh_token_cookie = APIKeyCookie(
    name="refresh_token",
    auto_error=False,
    scheme_name="Bearer",
    description="Refresh token for authentication",
)


class Dependencies:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.auth_crud = get_auth_crud(db)
        self.mysql_manager = mysql_manager
        self.security_manager = security_manager
        self.logger = logger_manager.get_logger(__name__)
    
    async def get_current_user(
        self,
        access_token: str = Depends(get_access_token_cookie),
        db: AsyncSession = Depends(mysql_manager.get_db),
    ):
        """Getcurrentuser(needauthentication)"""
        self.logger.info(
            f"get_current_user called with access_token: "
            f"{'***' if access_token else 'None'}"
        )
        
        if not access_token:
            self.logger.warning("No access_token provided in request")
            raise HTTPException(
                status_code=401,
                detail="Unauthorized access",
            )
        
        # Validate access token
        try:
            self.logger.info("Attempting to decode access token")
            token_data = security_manager.decode_token(access_token)
            
            if token_data:
                self.logger.info(
                    f"Token decoded successfully, user_id: {token_data.get('user_id')}"
                )
                user_id = token_data.get("user_id")
                
                if user_id:
                    self.logger.info(f"Validating token in database for user_id: {user_id}")
                    
                    # Validate access token validity in database
                    valid_access_token = await db.execute(
                        select(Token).where(
                            Token.user_id == user_id,
                            Token.type == TokenType.access,
                            Token.is_active == True,
                            Token.expired_at > func.utc_timestamp(),
                        )
                    )
                    valid_token = valid_access_token.scalar_one_or_none()
                    
                    if valid_token:
                        self.logger.info(f"Valid token found in database: {valid_token.id}")
                        
                        # Get user information from database
                        user = await self.auth_crud.get_user_by_id(user_id)
                        
                        if (
                            user
                            and user.is_active
                            and user.is_verified
                            and not user.is_deleted
                        ):
                            self.logger.info(f"User authenticated via access token: {user.email}")
                            return user
                        else:
                            self.logger.warning(
                                f"User validation failed - "
                                f"active: {user.is_active if user else 'N/A'}, "
                                f"verified: {user.is_verified if user else 'N/A'}, "
                                f"deleted: {user.is_deleted if user else 'N/A'}"
                            )
                    else:
                        self.logger.warning(f"No valid token found in database for user_id: {user_id}")
                else:
                    self.logger.warning("No user_id found in decoded token")
            else:
                self.logger.warning("Token decode returned None")
        except Exception as e:
            self.logger.warning(f"Access token validation failed: {str(e)}")
        
        # If all tokens are invalid, raise unauthorized error
        self.logger.warning("All token validation attempts failed")
        raise HTTPException(
            status_code=401,
            detail="Unauthorized access",
        )
    
    async def cleanup_tokens(
        self,
        response: Response,
    ) -> bool:
        """cleanuser tokens(logouthouruse)"""
        response.delete_cookie(
            "access_token",
            domain=settings.domain.COOKIE_DOMAIN,
            path="/",
        )
        self.logger.info("Access token cookie deleted")
        
        response.delete_cookie(
            "refresh_token",
            domain=settings.domain.COOKIE_DOMAIN,
            path="/",
        )
        self.logger.info("Refresh token cookie deleted")
        
        return True

