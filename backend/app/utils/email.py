
"""邮件工具模块：提供邮件模板加载、SMTP发送、批量邮件等功能"""
import asyncio
import smtplib
import ssl
from abc import ABC, abstractmethod
from asyncio import TimeoutError as AsyncioTimeoutError
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional, Union, Any

from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from app.core.config.settings import settings
from app.core.logger import logger_manager

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_TEMPLATE_DIR = BASE_DIR / "static" / "email_template"

class EmailBackend(ABC):
    """邮件发送后端抽象基类：定义邮件发送和连接测试的接口"""
    
    @abstractmethod
    async def send_email(self, message: MIMEMultipart) -> None:
        """异步发送邮件
        
        Args:
            message: MIMEMultipart邮件对象
            
        Raises:
            HTTPException: 当邮件发送失败时
        """
        pass
    
    @abstractmethod
    def test_connection(self) -> bool:
        """测试邮件服务连接是否正常
        
        Returns:
            bool: 连接成功返回True，失败返回False
        """
        pass


class EmailTemplateLoader:
    """邮件模板加载器：使用Jinja2加载和渲染邮件HTML模板，支持模板缓存"""
    
    def __init__(self, template_dir: Union[str, Path] | None = None):
        """初始化模板加载器
        
        Args:
            template_dir: 模板目录路径，默认使用 static/email_template
        """
        if template_dir is None:
            self.template_dir = DEFAULT_TEMPLATE_DIR
        else:
            path = Path(template_dir)
            self.template_dir = path if path.is_absolute() else BASE_DIR / path
        self._template_cache: Dict[str, Any] = {}
        
        # 目录不存在时自动创建
        self.template_dir.mkdir(parents=True, exist_ok=True)
        
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
    
    def render_template(self, template_name: str, **kwargs) -> str:
        """渲染邮件模板
        
        Args:
            template_name: 模板名称（不含.html后缀）
            **kwargs: 模板渲染所需的变量
            
        Returns:
            str: 渲染后的HTML字符串
            
        Raises:
            FileNotFoundError: 当模板文件不存在时
            ValueError: 当模板渲染失败时
        """
        try:
            if template_name not in self._template_cache:
                template = self.env.get_template(f"{template_name}.html")
                self._template_cache[template_name] = template
            else:
                template = self._template_cache[template_name]
            
            return template.render(**kwargs)
        except TemplateNotFound:
            raise FileNotFoundError(
                f"Template '{template_name}' not found in '{self.template_dir}'"
            )
        except Exception as e:
            raise ValueError(f"Failed to render template '{template_name}': {str(e)}")
    
    def template_exists(self, template_name: str) -> bool:
        """检查模板是否存在
        
        Args:
            template_name: 模板名称（不含.html后缀）
            
        Returns:
            bool: 模板存在返回True，否则返回False
        """
        return (self.template_dir / f"{template_name}.html").exists()
    
    def list_templates(self) -> List[str]:
        """列出所有可用的邮件模板
        
        Returns:
            List[str]: 模板名称列表（不含.html后缀）
        """
        return [f.stem for f in self.template_dir.glob("*.html")]
    
    def clear_cache(self) -> None:
        """清空模板缓存"""
        self._template_cache.clear()


class SMTPEmailBackend(EmailBackend):
    """SMTP邮件发送后端：基于smtplib实现邮件发送，支持SSL/TLS加密"""
    
    def __init__(self, email_settings):
        """初始化SMTP邮件后端
        
        Args:
            email_settings: 邮件配置对象，包含SMTP服务器、端口、认证信息等
        """
        self.email_settings = email_settings
        self.logger = logger_manager.get_logger(__name__)
    
    def _create_ssl_context(self) -> ssl.SSLContext:
        """创建SSL/TLS上下文
        
        根据配置设置证书验证模式
        
        Returns:
            ssl.SSLContext: SSL上下文对象
        """
        ssl_context = ssl.create_default_context()
        
        cert_reqs = getattr(
            self.email_settings, "EMAIL_SSL_CERT_REQS", "required"
        )
        
        if cert_reqs == "required":
            ssl_context.verify_mode = ssl.CERT_REQUIRED
        elif cert_reqs == "optional":
            ssl_context.verify_mode = ssl.CERT_OPTIONAL
        else:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        
        return ssl_context
    
    def _create_smtp_server(self, ssl_context: ssl.SSLContext) -> smtplib.SMTP:
        """创建SMTP服务器连接
        
        根据配置选择使用SSL或TLS加密方式
        
        Args:
            ssl_context: SSL上下文对象
            
        Returns:
            smtplib.SMTP: SMTP服务器连接对象
        """
        use_ssl = getattr(self.email_settings, "EMAIL_USE_SSL", False)
        use_tls = getattr(self.email_settings, "EMAIL_USE_TLS", True)
        timeout = getattr(self.email_settings, "EMAIL_TIMEOUT", 30)
        
        if use_ssl:
            server = smtplib.SMTP_SSL(
                self.email_settings.EMAIL_HOST,
                self.email_settings.EMAIL_PORT,
                timeout=timeout,
                context=ssl_context,
            )
        else:
            server = smtplib.SMTP(
                self.email_settings.EMAIL_HOST,
                self.email_settings.EMAIL_PORT,
                timeout=timeout,
            )
            if use_tls:
                server.starttls(context=ssl_context)
        
        return server
    
    async def send_email(self, message: MIMEMultipart) -> None:
        """异步发送邮件
        
        Args:
            message: MIMEMultipart邮件对象
            
        Raises:
            HTTPException: 当邮件发送失败时（认证失败、连接失败等）
        """
        server = None
        try:
            ssl_context = self._create_ssl_context()
            server = self._create_smtp_server(ssl_context)
            
            # 开发环境启用调试模式
            if hasattr(settings, "debug") and settings.debug:
                server.set_debuglevel(1)
            
            server.login(
                self.email_settings.EMAIL_HOST_USER,
                self.email_settings.EMAIL_HOST_PASSWORD.get_secret_value(),
            )
            
            server.sendmail(
                self.email_settings.EMAIL_HOST_USER,
                message["To"],
                message.as_string()
            )
            
            self.logger.info(f"Email sent successfully to {message['To']}")
            
        except smtplib.SMTPAuthenticationError as e:
            self.logger.error(f"SMTP authentication failed: {e}")
            raise HTTPException(
                status_code=400,
                detail="Email authentication failed"
            )
        except smtplib.SMTPConnectError as e:
            self.logger.error(f"SMTP connection failed: {e}")
            raise HTTPException(
                status_code=400,
                detail="Email connection failed"
            )
        except smtplib.SMTPException as e:
            self.logger.error(f"SMTP error: {e}")
            raise HTTPException(
                status_code=400,
                detail="Email sending failed"
            )
        except Exception as e:
            self.logger.error(f"Unexpected error sending email: {e}")
            raise HTTPException(
                status_code=400,
                detail="Email sending failed"
            )
        finally:
            if server:
                try:
                    server.quit()
                except Exception as e:
                    self.logger.warning(f"Error closing SMTP connection: {e}")
    
    def test_connection(self) -> bool:
        """测试SMTP连接是否正常
        
        Returns:
            bool: 连接成功返回True，失败返回False
        """
        try:
            ssl_context = self._create_ssl_context()
            server = self._create_smtp_server(ssl_context)
            server.login(
                self.email_settings.EMAIL_HOST_USER,
                self.email_settings.EMAIL_HOST_PASSWORD.get_secret_value(),
            )
            server.quit()
            return True
        except Exception as e:
            self.logger.error(f"SMTP connection test failed: {e}")
            return False


class EmailMessage:
    """邮件消息构建器：使用流式接口构建MIME邮件，支持HTML/纯文本内容和附件"""
    
    def __init__(self, subject: str, recipient: str, sender: str):
        """初始化邮件消息
        
        Args:
            subject: 邮件主题
            recipient: 收件人邮箱
            sender: 发件人邮箱
        """
        self.subject = subject
        self.recipient = recipient
        self.sender = sender
        self.html_content: Optional[str] = None
        self.text_content: Optional[str] = None
        self.attachments: List[Dict[str, Any]] = []
    
    def set_html_content(self, content: str) -> "EmailMessage":
        """设置HTML邮件内容
        
        Args:
            content: HTML内容字符串
            
        Returns:
            EmailMessage: 返回自身以支持链式调用
        """
        self.html_content = content
        return self
    
    def set_text_content(self, content: str) -> "EmailMessage":
        """设置纯文本邮件内容
        
        Args:
            content: 纯文本内容字符串
            
        Returns:
            EmailMessage: 返回自身以支持链式调用
        """
        self.text_content = content
        return self
    
    def add_attachment(
        self,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> "EmailMessage":
        """添加邮件附件
        
        Args:
            filename: 附件文件名
            content: 附件内容（字节数据）
            content_type: 附件MIME类型，默认为application/octet-stream
            
        Returns:
            EmailMessage: 返回自身以支持链式调用
        """
        self.attachments.append({
            "filename": filename,
            "content": content,
            "content_type": content_type
        })
        return self
    
    def build(self) -> MIMEMultipart:
        """构建MIMEMultipart邮件对象
        
        Returns:
            MIMEMultipart: 构建完成的邮件对象
        """
        msg = MIMEMultipart("alternative")
        msg["From"] = self.sender
        msg["To"] = self.recipient
        msg["Subject"] = self.subject
        
        if self.text_content:
            msg.attach(MIMEText(self.text_content, "plain"))
        
        if self.html_content:
            msg.attach(MIMEText(self.html_content, "html"))
        
        # 如有附件则添加
        for attachment in self.attachments:
            from email.mime.base import MIMEBase
            from email import encoders
            from email.header import Header
            
            part = MIMEBase(*attachment["content_type"].split("/", 1))
            part.set_payload(attachment["content"])
            encoders.encode_base64(part)
            
            # 正确编码文件名，兼容非 ASCII 字符
            filename = attachment["filename"]
            encoded_filename = Header(filename, "utf-8").encode()
            part.add_header(
                "Content-Disposition",
                "attachment",
                filename=encoded_filename
            )
            msg.attach(part)
        
        return msg


class EmailService:
    """邮件服务类：整合模板加载、邮件构建和发送功能，提供高级邮件发送接口"""
    
    def __init__(
        self,
        backend: EmailBackend,
        config_settings,
        template_loader: Optional[EmailTemplateLoader] = None,
    ):
        """初始化邮件服务
        
        Args:
            backend: 邮件发送后端实例
            config_settings: 配置对象
            template_loader: 模板加载器实例，可选，默认使用EmailTemplateLoader
        """
        self.backend = backend
        self.settings = config_settings
        self.template_loader = template_loader or EmailTemplateLoader()
        self.logger = logger_manager.get_logger(__name__)
    
    def _prepare_template_variables(
        self,
        recipient: str,
        code: str = "",
        **extra_vars
    ) -> Dict[str, str]:
        """准备邮件模板变量
        
        Args:
            recipient: 收件人邮箱
            code: 验证码（可选）
            **extra_vars: 额外的模板变量
            
        Returns:
            Dict[str, str]: 包含所有模板变量的字典
        """
        base_vars = {
            "recipient": recipient,
            "code": code,
            "expiration_minutes": str(
                getattr(self.settings.email, "EMAIL_EXPIRATION", 3600) // 60
            ),
            "year": str(datetime.now().year),
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "current_time": datetime.now().strftime("%H:%M:%S"),
            "app_name": getattr(self.settings.app, "APP_NAME", "Our App"),
        }
        
        # 合并额外传入的模板变量
        base_vars.update(extra_vars)
        return base_vars
    
    def _create_email_message(
        self,
        subject: str,
        recipient: str,
        template_name: str,
        template_vars: Dict[str, str],
    ) -> EmailMessage:
        """创建邮件消息对象
        
        Args:
            subject: 邮件主题
            recipient: 收件人邮箱
            template_name: 模板名称
            template_vars: 模板变量
            
        Returns:
            EmailMessage: 构建好的邮件消息对象
            
        Raises:
            HTTPException: 当模板不存在或渲染失败时
        """
        try:
            # 检查模板是否存在
            if not self.template_loader.template_exists(template_name):
                raise HTTPException(
                    status_code=404,
                    detail="Email template not found"
                )
            
            html_content = self.template_loader.render_template(
                template_name,
                **template_vars
            )
        except (FileNotFoundError, ValueError) as e:
            self.logger.error(f"Error rendering template: {e}")
            raise HTTPException(
                status_code=400,
                detail="Email template error"
            )
        
        return EmailMessage(
            subject,
            recipient,
            self.settings.email.EMAIL_HOST_USER
        ).set_html_content(html_content)
    
    async def send_email(
        self,
        subject: str,
        recipient: str,
        template: str,
        code: str = "",
        retries: int = 3,
        retry_delay: int = 2,
        timeout: Optional[int] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        **template_vars,
    ) -> None:
        """发送邮件（带重试机制）
        
        Args:
            subject: 邮件主题
            recipient: 收件人邮箱
            template: 邮件模板名称
            code: 验证码（可选）
            retries: 重试次数，默认3次
            retry_delay: 重试延迟（秒），默认2秒
            timeout: 超时时间（秒），默认使用配置中的值
            attachments: 附件列表，每个附件包含filename、content、content_type
            **template_vars: 额外的模板变量
            
        Raises:
            ValueError: 当收件人邮箱或主题无效时
            HTTPException: 当邮件发送失败时
        """
        if timeout is None:
            timeout = getattr(self.settings.email, "EMAIL_TIMEOUT", 30)
        
        # 校验输入参数
        if not recipient or "@" not in recipient:
            raise ValueError("Invalid email address")
        
        if not subject.strip():
            raise ValueError("Email subject cannot be empty")
        
        # 准备邮件模板变量
        template_variables = self._prepare_template_variables(
            recipient,
            code,
            **template_vars
        )
        
        email_message = self._create_email_message(
            subject,
            recipient,
            template,
            template_variables
        )
        
        # 若提供附件则添加
        if attachments:
            for attachment in attachments:
                email_message.add_attachment(
                    filename=attachment["filename"],
                    content=attachment["content"],
                    content_type=attachment.get(
                        "content_type",
                        "application/octet-stream"
                    ),
                )
        
        mime_message = email_message.build()
        
        # 带指数退避的重试机制
        last_exception = None
        for attempt in range(retries):
            try:
                await asyncio.wait_for(
                    self.backend.send_email(mime_message),
                    timeout=timeout
                )
                self.logger.info(
                    f"Email sent successfully to {recipient} "
                    f"using template '{template}'"
                )
                return
            except AsyncioTimeoutError as e:
                last_exception = e
                self.logger.warning(
                    f"Timeout error while sending email to {recipient}, "
                    f"attempt {attempt + 1}/{retries}"
                )
            except HTTPException as e:
                # HTTP 异常立即抛出
                raise e
            except Exception as e:
                last_exception = e
                self.logger.error(
                    f"Error sending email to {recipient}, "
                    f"attempt {attempt + 1}/{retries}: {e}"
                )
            
            if attempt < retries - 1:
                # 指数退避等待
                delay = retry_delay * (2 ** attempt)
                await asyncio.sleep(delay)
        
        self.logger.error(
            f"Failed to send email to {recipient} after {retries} attempts"
        )
        raise HTTPException(
            status_code=400,
            detail="Email sending failed"
        )
    
    async def send_bulk_email(
        self,
        subject: str,
        recipients: List[str],
        template: str,
        code: str = "",
        batch_size: int = 10,
        **template_vars,
    ) -> Dict[str, Any]:
        """批量发送邮件
        
        Args:
            subject: 邮件主题
            recipients: 收件人邮箱列表
            template: 邮件模板名称
            code: 验证码（可选）
            batch_size: 每批发送的邮件数量，默认10
            **template_vars: 额外的模板变量
            
        Returns:
            Dict[str, Any]: 包含发送结果的字典，包括success、failed和total
        """
        results = {
            "success": [],
            "failed": [],
            "total": len(recipients)
        }
        
        for i in range(0, len(recipients), batch_size):
            batch = recipients[i:i + batch_size]
            tasks = []
            
            for recipient in batch:
                task = self.send_email(
                    subject=subject,
                    recipient=recipient,
                    template=template,
                    code=code,
                    **template_vars,
                )
                tasks.append(task)
            
            # 执行当前批次发送
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for recipient, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    results["failed"].append({
                        "recipient": recipient,
                        "error": str(result)
                    })
                else:
                    results["success"].append(recipient)
        
        return results
    
    def test_connection(self) -> bool:
        """测试邮件服务连接
        
        Returns:
            bool: 连接成功返回True，失败返回False
        """
        return self.backend.test_connection()
    
    def get_available_templates(self) -> List[str]:
        """获取所有可用的邮件模板
        
        Returns:
            List[str]: 模板名称列表
        """
        return self.template_loader.list_templates()
    
    def clear_template_cache(self) -> None:
        """清空模板缓存"""
        self.template_loader.clear_cache()


# 全局邮件服务实例
_email_service_instance = None


def get_email_service() -> EmailService:
    """获取邮件服务单例
    
    Returns:
        EmailService: 邮件服务实例
    """
    global _email_service_instance
    
    if _email_service_instance is None:
        from app.core.config.settings import settings
        
        _email_service_instance = EmailService(
            backend=SMTPEmailBackend(settings.email),
            config_settings=settings,
            template_loader=EmailTemplateLoader(),
        )
    
    return _email_service_instance


# 为向后兼容保留：通过属性延迟获取服务实例
class EmailServiceProxy:
    """邮件服务代理类：提供延迟加载的邮件服务访问"""
    
    def __getattr__(self, name):
        """动态获取邮件服务的属性
        
        Args:
            name: 属性名称
            
        Returns:
            邮件服务的对应属性
        """
        service = get_email_service()
        return getattr(service, name)


email_service = EmailServiceProxy()

