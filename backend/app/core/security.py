
"""安全模块 - 密码验证、密码哈希和JWT令牌管理"""
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Union
from jose import jwt
from jose.exceptions import JWTError, ExpiredSignatureError
import argon2
from app.core.logger import logger_manager
from app.core.config.settings import settings

logger = logger_manager.get_logger(__name__)


class PasswordValidator:
    """密码强度验证器 - 验证密码是否满足安全要求"""
    
    PASSWORD_PATTERNS = {
        "uppercase": r"[A-Z]",
        "lowercase": r"[a-z]",
        "digit": r"\d",
        "special": r"[!@#$%^&*(),.?\":{}|<>]",
    }
    
    def __init__(self, min_length: int = 8):
        """初始化密码验证器
        
        Args:
            min_length: 密码最小长度，默认为8
        """
        self.min_length = min_length
        self.logger = logger
    
    def validate(self, password: str) -> bool:
        """验证密码强度
        
        Args:
            password: 待验证的密码
            
        Returns:
            bool: 验证通过返回True
            
        Raises:
            ValueError: 密码不满足要求时抛出异常
        """
        self._check_length(password)
        self._check_uppercase(password)
        self._check_lowercase(password)
        self._check_digit(password)
        self._check_special_char(password)
        self.logger.info("Password passed strength validation.")
        return True
    
    def _check_length(self, password: str):
        """检查密码长度"""
        if len(password) < self.min_length:
            self.logger.warning("Password validation failed: too short.")
            raise ValueError(
                f"Password must be at least {self.min_length} characters long."
            )
    
    def _check_uppercase(self, password: str):
        """检查是否包含大写字母"""
        if not re.search(self.PASSWORD_PATTERNS["uppercase"], password):
            self.logger.warning("Password validation failed: no uppercase letter.")
            raise ValueError("Password must contain at least one uppercase letter.")
    
    def _check_lowercase(self, password: str):
        """检查是否包含小写字母"""
        if not re.search(self.PASSWORD_PATTERNS["lowercase"], password):
            self.logger.warning("Password validation failed: no lowercase letter.")
            raise ValueError("Password must contain at least one lowercase letter.")
    
    def _check_digit(self, password: str):
        """检查是否包含数字"""
        if not re.search(self.PASSWORD_PATTERNS["digit"], password):
            self.logger.warning("Password validation failed: no digit.")
            raise ValueError("Password must contain at least one digit.")
    
    def _check_special_char(self, password: str):
        """检查是否包含特殊字符"""
        if not re.search(self.PASSWORD_PATTERNS["special"], password):
            self.logger.warning("Password validation failed: no special character.")
            raise ValueError("Password must contain at least one special character.")


class PasswordHasher:
    """密码哈希器 - 使用Argon2算法进行密码哈希和验证"""
    
    def __init__(self):
        """初始化密码哈希器，配置Argon2参数"""
        self.logger = logger_manager.get_logger(__name__)
        # useArgon2 - highperformanceconfiguration
        self.ph = argon2.PasswordHasher(
            time_cost=2,  # Time cost (iteration count) - optimize performance
            memory_cost=65536,  # Memory cost (64MB)
            parallelism=1,  # Parallelism
            hash_len=32,  # Hash length
            salt_len=16,  # Salt length
        )
        self.logger.info("Using Argon2 for password hashing")
    
    def hash(self, password: str) -> str:
        """哈希密码
        
        Args:
            password: 明文密码
            
        Returns:
            str: 哈希后的密码
            
        Raises:
            Exception: 哈希失败时抛出异常
        """
        try:
            hashed = self.ph.hash(password)
            self.logger.debug("Password hashed successfully with Argon2")
            return hashed
        except Exception as e:
            self.logger.error(f"Error hashing password with Argon2: {e}")
            raise
    
    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码
        
        Args:
            plain_password: 明文密码
            hashed_password: 哈希后的密码
            
        Returns:
            bool: 验证成功返回True，失败返回False
        """
        try:
            self.ph.verify(hashed_password, plain_password)
            return True
        except argon2.exceptions.VerifyMismatchError:
            self.logger.debug("Password verification failed")
            return False
        except Exception as e:
            self.logger.error(f"Error verifying password: {e}")
            return False


class JWTManager:
    """JWT令牌管理器 - 创建和验证JWT访问令牌和刷新令牌"""
    
    def __init__(
        self,
        secret_key: str,
        algorithm: str,
        issuer: str,
        audience: str,
        access_token_expiry: int,
        refresh_token_expiry: int,
    ):
        """初始化JWT管理器
        
        Args:
            secret_key: JWT密钥
            algorithm: JWT算法
            issuer: JWT发行者
            audience: JWT受众
            access_token_expiry: 访问令牌过期时间（秒）
            refresh_token_expiry: 刷新令牌过期时间（秒）
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.issuer = issuer
        self.audience = audience
        self.access_token_expiry = access_token_expiry
        self.refresh_token_expiry = refresh_token_expiry
        self.logger = logger
    
    def timestamp_to_datetime(self, timestamp: int) -> datetime:
        """将时间戳转换为UTC日期时间
        
        Args:
            timestamp: Unix时间戳
            
        Returns:
            datetime: UTC日期时间对象
        """
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    
    def create_access_token(self, data: Dict) -> tuple[str, datetime]:
        """创建访问令牌
        
        Args:
            data: 要编码到令牌中的数据
            
        Returns:
            tuple: (令牌字符串, 过期时间datetime对象)
        """
        return self._create_token(data, self.access_token_expiry, "access")
    
    def create_refresh_token(self, data: Dict) -> tuple[str, datetime]:
        """创建刷新令牌
        
        Args:
            data: 要编码到令牌中的数据
            
        Returns:
            tuple: (令牌字符串, 过期时间datetime对象)
        """
        return self._create_token(data, self.refresh_token_expiry, "refresh")
    
    def _create_token(
        self, data: Dict, expires_in_seconds: int, token_type: str
    ) -> tuple[str, datetime]:
        """创建JWT令牌的内部方法
        
        Args:
            data: 要编码到令牌中的数据
            expires_in_seconds: 令牌有效期（秒）
            token_type: 令牌类型（access或refresh）
            
        Returns:
            tuple: (令牌字符串, 过期时间datetime对象)
        """
        exp_time = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
        # Convert to UTC timestamp
        payload = {
            **data,
            "exp": int(exp_time.timestamp()),
            "iss": self.issuer,
            "aud": self.audience,
            "token_type": token_type,
        }
        encoded_jwt = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        self.logger.info(
            f"{token_type} token created for user: {data.get('user_id')} "
            f"with expiration: {payload['exp']}"
        )
        return encoded_jwt, exp_time
    
    def decode_token(
        self, token: str, expected_jti: Optional[str] = None
    ) -> Union[Dict, None]:
        """解码并验证JWT令牌
        
        Args:
            token: JWT令牌字符串
            expected_jti: 期望的JWT ID（可选）
            
        Returns:
            Dict or None: 解码后的令牌数据，验证失败返回None
        """
        try:
            decoded_token = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["iss", "aud", "exp"]},
            )
            
            if expected_jti and decoded_token.get("jti") != expected_jti:
                self.logger.error("JTI mismatch. Token invalid.")
                return None
            
            self.logger.info(
                f"Token decoded successfully for user_id: {decoded_token.get('user_id')}"
            )
            return decoded_token
        except ExpiredSignatureError:
            self.logger.warning("JWT token has expired.")
        except JWTError as e:
            self.logger.error(f"Invalid JWT token: {e}")
        return None


class SecurityManager:
    """安全管理器 - 统一管理密码验证、密码哈希和JWT令牌"""
    
    def __init__(self, settings):
        """初始化安全管理器
        
        Args:
            settings: 应用配置对象
        """
        self.validator = PasswordValidator()
        self.hasher = PasswordHasher()
        self.jwt_manager = JWTManager(
            secret_key=settings.jwt.JWT_SECRET_KEY.get_secret_value(),
            algorithm=settings.jwt.JWT_ALGORITHM,
            issuer=settings.jwt.JWT_ISSUER,
            audience=settings.jwt.JWT_AUDIENCE,
            access_token_expiry=settings.jwt.JWT_ACCESS_TOKEN_EXPIRATION,
            refresh_token_expiry=settings.jwt.JWT_REFRESH_TOKEN_EXPIRATION,
        )
    
    def validate_password(self, password: str) -> bool:
        """验证密码强度
        
        Args:
            password: 待验证的密码
            
        Returns:
            bool: 验证通过返回True
        """
        return self.validator.validate(password)
    
    def hash_password(self, password: str) -> str:
        """哈希密码
        
        Args:
            password: 明文密码
            
        Returns:
            str: 哈希后的密码
        """
        return self.hasher.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码
        
        Args:
            plain_password: 明文密码
            hashed_password: 哈希后的密码
            
        Returns:
            bool: 验证成功返回True
        """
        return self.hasher.verify(plain_password, hashed_password)
    
    def create_access_token(self, data: Dict) -> tuple[str, datetime]:
        """创建访问令牌
        
        Args:
            data: 要编码到令牌中的数据
            
        Returns:
            tuple: (令牌字符串, 过期时间datetime对象)
        """
        return self.jwt_manager.create_access_token(data)
    
    def create_refresh_token(self, data: Dict) -> tuple[str, datetime]:
        """创建刷新令牌
        
        Args:
            data: 要编码到令牌中的数据
            
        Returns:
            tuple: (令牌字符串, 过期时间datetime对象)
        """
        return self.jwt_manager.create_refresh_token(data)
    
    def decode_token(
        self, token: str, expected_jti: Optional[str] = None
    ) -> Union[Dict, None]:
        """解码并验证JWT令牌
        
        Args:
            token: JWT令牌字符串
            expected_jti: 期望的JWT ID（可选）
            
        Returns:
            Dict or None: 解码后的令牌数据，验证失败返回None
        """
        return self.jwt_manager.decode_token(token, expected_jti)


security_manager = SecurityManager(settings)


# Convenience functions (backward compatible)
def get_password_hash(password: str) -> str:
    """获取密码哈希（向后兼容函数）
    
    Args:
        password: 明文密码
        
    Returns:
        str: 哈希后的密码
    """
    return security_manager.hash_password(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码（向后兼容函数）
    
    Args:
        plain_password: 明文密码
        hashed_password: 哈希后的密码
        
    Returns:
        bool: 验证成功返回True
    """
    return security_manager.verify_password(plain_password, hashed_password)

