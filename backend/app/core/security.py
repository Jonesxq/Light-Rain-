
"""core/security.py."""
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
    
    """PasswordValidator ??"""
    PASSWORD_PATTERNS = {
        "uppercase": r"[A-Z]",
        "lowercase": r"[a-z]",
        "digit": r"\d",
        "special": r"[!@#$%^&*(),.?\":{}|<>]",
    }
    
    def __init__(self, min_length: int = 8):
        """__init__ ???"""
        self.min_length = min_length
        self.logger = logger
    
    def validate(self, password: str) -> bool:
        """validate ???"""
        self._check_length(password)
        self._check_uppercase(password)
        self._check_lowercase(password)
        self._check_digit(password)
        self._check_special_char(password)
        self.logger.info("Password passed strength validation.")
        return True
    
    def _check_length(self, password: str):
        """_check_length ???"""
        if len(password) < self.min_length:
            self.logger.warning("Password validation failed: too short.")
            raise ValueError(
                f"Password must be at least {self.min_length} characters long."
            )
    
    def _check_uppercase(self, password: str):
        """_check_uppercase ???"""
        if not re.search(self.PASSWORD_PATTERNS["uppercase"], password):
            self.logger.warning("Password validation failed: no uppercase letter.")
            raise ValueError("Password must contain at least one uppercase letter.")
    
    def _check_lowercase(self, password: str):
        """_check_lowercase ???"""
        if not re.search(self.PASSWORD_PATTERNS["lowercase"], password):
            self.logger.warning("Password validation failed: no lowercase letter.")
            raise ValueError("Password must contain at least one lowercase letter.")
    
    def _check_digit(self, password: str):
        """_check_digit ???"""
        if not re.search(self.PASSWORD_PATTERNS["digit"], password):
            self.logger.warning("Password validation failed: no digit.")
            raise ValueError("Password must contain at least one digit.")
    
    def _check_special_char(self, password: str):
        """_check_special_char ???"""
        if not re.search(self.PASSWORD_PATTERNS["special"], password):
            self.logger.warning("Password validation failed: no special character.")
            raise ValueError("Password must contain at least one special character.")


class PasswordHasher:
    
    """PasswordHasher ??"""
    def __init__(self):
        """__init__ ???"""
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
        """hash ???"""
        try:
            hashed = self.ph.hash(password)
            self.logger.debug("Password hashed successfully with Argon2")
            return hashed
        except Exception as e:
            self.logger.error(f"Error hashing password with Argon2: {e}")
            raise
    
    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """verify ???"""
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
    
    """JWTManager ??"""
    def __init__(
        self,
        secret_key: str,
        algorithm: str,
        issuer: str,
        audience: str,
        access_token_expiry: int,
        refresh_token_expiry: int,
    ):
        """__init__ ???"""
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.issuer = issuer
        self.audience = audience
        self.access_token_expiry = access_token_expiry
        self.refresh_token_expiry = refresh_token_expiry
        self.logger = logger
    
    def timestamp_to_datetime(self, timestamp: int) -> datetime:
        """timestamp_to_datetime ???"""
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    
    def create_access_token(self, data: Dict) -> tuple[str, datetime]:
        """create_access_token ???"""
        return self._create_token(data, self.access_token_expiry, "access")
    
    def create_refresh_token(self, data: Dict) -> tuple[str, datetime]:
        """create_refresh_token ???"""
        return self._create_token(data, self.refresh_token_expiry, "refresh")
    
    def _create_token(
        self, data: Dict, expires_in_seconds: int, token_type: str
    ) -> tuple[str, datetime]:
        """_create_token ???"""
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
        """decode_token ???"""
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
    
    """SecurityManager ??"""
    def __init__(self, settings):
        """__init__ ???"""
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
        """validate_password ???"""
        return self.validator.validate(password)
    
    def hash_password(self, password: str) -> str:
        """hash_password ???"""
        return self.hasher.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """verify_password ???"""
        return self.hasher.verify(plain_password, hashed_password)
    
    def create_access_token(self, data: Dict) -> tuple[str, datetime]:
        """create_access_token ???"""
        return self.jwt_manager.create_access_token(data)
    
    def create_refresh_token(self, data: Dict) -> tuple[str, datetime]:
        """create_refresh_token ???"""
        return self.jwt_manager.create_refresh_token(data)
    
    def decode_token(
        self, token: str, expected_jti: Optional[str] = None
    ) -> Union[Dict, None]:
        """decode_token ???"""
        return self.jwt_manager.decode_token(token, expected_jti)


security_manager = SecurityManager(settings)


# Convenience functions (backward compatible)
def get_password_hash(password: str) -> str:
    """get_password_hash ???"""
    return security_manager.hash_password(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """verify_password ???"""
    return security_manager.verify_password(plain_password, hashed_password)

