from typing import Optional

from pydantic import BaseModel, Field

from .enum import EmailEncryptionEnum


class CustomSMTPConfig(BaseModel):
    enable: bool = False
    "是否启用自定义 SMTP"

    server: str = ""
    "SMTP 服务器地址"

    ssl_port: int = 465
    "SMTP 服务器端口号"

    encryption: EmailEncryptionEnum = EmailEncryptionEnum.SSL_TLS
    """
    SMTP 加密方式
    
    传入一个字符串，将会自动转换为对应的枚举类型。
    例如：
        - SSL/TLS (按理来说是不是应该分开？)
        - STARTTLS
    """


class EmailConfig(BaseModel):
    account: str = ""
    "邮箱账号"

    pass_code: str = ""
    "邮箱授权码"

    recipient: list[str] = []
    "收件人邮箱列表"

    custom_smtp_server: Optional[CustomSMTPConfig] = Field(
        default_factory=CustomSMTPConfig
    )
    "自定义 SMTP 服务器"

    mail_subject: str = "[Mower通知]"
    "邮件主题"
