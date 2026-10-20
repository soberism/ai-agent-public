"""文件主动内容及全局邮箱的账号边界，不连接外部邮件或模型。"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.api.routes import documents, mail
from backend.core.security import APIError, settings
from backend.features.documents.preview import preview_type


@pytest.mark.parametrize(
    "media",
    ["text/html", "image/svg+xml", "application/pdf", "application/octet-stream"],
)
def test_untrusted_content_is_downloaded_and_sandboxed(monkeypatch, media):
    raw = b'<html><script>document.title="audit"</script></html>'
    row = SimpleNamespace(content=raw, media_type=media, name="audit.html")
    monkeypatch.setattr(documents, "material_owned", lambda *_: row)
    response = documents.content(uuid4(), object(), object())
    assert response.body == raw
    assert response.headers["content-disposition"].startswith("attachment")
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in response.headers["content-security-policy"]
    assert "allow-scripts" not in response.headers["content-security-policy"]


def test_preview_uses_magic_not_declared_mime(monkeypatch):
    raw = b"\x89PNG\r\n\x1a\nsynthetic"
    monkeypatch.setattr(
        documents,
        "material_owned",
        lambda *_: SimpleNamespace(
            content=raw, media_type="text/html", name="image.png"
        ),
    )
    response = documents.content(uuid4(), object(), object())
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"].startswith("inline")
    assert (
        documents.content(uuid4(), object(), object(), download=True)
        .headers["content-disposition"]
        .startswith("attachment")
    )
    assert preview_type(b"<script>marker</script>", "image/png") is None
    assert preview_type(b"<script>marker</script>", "text/plain") == "text/plain"
    assert preview_type(b"\xff\x00", "text/plain") is None


def test_imap_is_off_without_bound_account(monkeypatch):
    monkeypatch.setattr(settings, "imap_owner_id", "")
    assert not mail.capabilities().imap


def test_imap_rejects_other_account_before_connecting(monkeypatch):
    owner, stranger = uuid4(), uuid4()
    monkeypatch.setattr(settings, "imap_owner_id", str(owner))
    monkeypatch.setattr(mail, "capabilities", lambda: SimpleNamespace(imap=True))
    monkeypatch.setattr(
        mail.imaplib,
        "IMAP4_SSL",
        lambda *a, **kw: pytest.fail("未授权账号不能连接邮箱"),
    )
    with pytest.raises(APIError) as denied:
        mail.scan(SimpleNamespace(id=stranger), object())
    assert denied.value.status == 403


def test_bound_imap_account_can_scan_readonly(monkeypatch):
    from unittest.mock import MagicMock

    from pydantic import SecretStr

    owner = uuid4()
    monkeypatch.setattr(settings, "imap_owner_id", str(owner))
    monkeypatch.setattr(settings, "imap_password", SecretStr("synthetic"))
    monkeypatch.setattr(mail, "capabilities", lambda: SimpleNamespace(imap=True))
    factory = MagicMock()
    client = factory.return_value.__enter__.return_value
    client.select.return_value = ("OK", [])
    client.search.return_value = ("OK", [b""])
    monkeypatch.setattr(mail.imaplib, "IMAP4_SSL", factory)
    db = MagicMock()
    assert mail.scan(SimpleNamespace(id=owner), db).imported == 0
    assert client.select.call_args.kwargs["readonly"] is True
    db.commit.assert_called_once()
