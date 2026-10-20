"""SMTP 接受邮件后才报告发送成功；不记录邮件正文。"""

import smtplib
import ssl
from email.message import EmailMessage

from backend.core.security import settings


def send_code(email, code):
    send_message(
        email,
        "注册邮箱验证码",
        f"您的注册验证码为：{code}\n10分钟内有效，请勿向他人透露。\n如非本人操作，请忽略此邮件。",
    )


def send_message(email, subject, body):
    message = EmailMessage()
    message["Subject"] = (
        subject if subject.startswith("【安排儿】") else f"【安排儿】{subject}"
    )
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(body)
    context = ssl.create_default_context()
    if settings.smtp_security == "ssl":
        connection = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=10, context=context
        )
    else:
        connection = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
    with connection as smtp:
        if settings.smtp_security == "starttls":
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
        smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        if smtp.send_message(message):
            raise smtplib.SMTPException("recipient rejected")
