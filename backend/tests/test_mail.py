import smtplib
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from backend.features.auth import mail


@pytest.mark.parametrize("security", ["ssl", "starttls"])
def test_smtp_uses_tls_and_rejects_refused_recipient(monkeypatch, security):
    monkeypatch.setattr(mail.settings, "smtp_security", security)
    monkeypatch.setattr(mail.settings, "smtp_from", "test@example.com")
    monkeypatch.setattr(mail.settings, "smtp_password", SecretStr("test-password"))
    connection = MagicMock()
    smtp = connection.__enter__.return_value
    smtp.send_message.return_value = {}
    factory = MagicMock(return_value=connection)
    monkeypatch.setattr(
        mail.smtplib, "SMTP_SSL" if security == "ssl" else "SMTP", factory
    )
    mail.send_code("recipient@example.com", "123456")
    assert smtp.send_message.call_args.args[0]["Subject"] == "【安排儿】注册邮箱验证码"
    assert factory.call_args.kwargs["timeout"] == 10
    if security == "starttls":
        assert smtp.starttls.call_args.kwargs["context"].check_hostname
        names = [call[0] for call in smtp.method_calls]
        assert (
            names.index("starttls") < names.index("login") < names.index("send_message")
        )
    else:
        assert factory.call_args.kwargs["context"].check_hostname
    smtp.send_message.return_value = {"recipient@example.com": (550, b"rejected")}
    with pytest.raises(smtplib.SMTPException):
        mail.send_code("recipient@example.com", "123456")
    smtp.set_debuglevel.assert_not_called()


def test_all_mail_subjects_have_one_app_prefix(monkeypatch):
    monkeypatch.setattr(mail.settings, "smtp_security", "ssl")
    monkeypatch.setattr(mail.settings, "smtp_from", "test@example.com")
    monkeypatch.setattr(mail.settings, "smtp_password", SecretStr("test-password"))
    connection = MagicMock()
    connection.__enter__.return_value.send_message.return_value = {}
    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", MagicMock(return_value=connection))
    for subject in ("事项提醒：开会", "【安排儿】事项提醒：开会"):
        mail.send_message("recipient@example.com", subject, "正文")
        assert connection.__enter__.return_value.send_message.call_args.args[0][
            "Subject"
        ] == ("【安排儿】事项提醒：开会")
