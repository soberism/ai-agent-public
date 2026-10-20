"""真实 HTTP 闭环检查；只连接指定的隔离测试 API，不启动任何基础服务。

用法：python infra/smoke_auth_todos.py http://127.0.0.1:8001
目标 API 必须连接专用测试库；输入两个可收件的测试邮箱，每次创建两个测试账号和待办，不删除既有数据。
"""

import json
import secrets
import sys
from getpass import getpass
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import uuid4


def main():
    if len(sys.argv) != 2:
        raise SystemExit("请传入隔离测试 API 地址，例如 http://127.0.0.1:8001")
    base = sys.argv[1].rstrip("/")
    password = secrets.token_urlsafe(24)
    accounts = [
        input(f"测试邮箱 {i + 1}（未注册且可收件）: ").strip() for i in range(2)
    ]
    clients = [build_opener(HTTPCookieProcessor(CookieJar())) for _ in accounts]

    def call(client, method, path, payload=None, expected=200, headers=None):
        request_headers = {"Origin": "http://localhost:9988", "X-App-Request": "1"}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        req = Request(
            base + "/api" + path, data=data, headers=request_headers, method=method
        )
        try:
            response = client.open(req, timeout=15)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            body = json.loads(raw) if raw else None
            # 不输出请求、Cookie 或密码；错误只报告状态和错误码。
            code = body.get("error", {}).get("code") if isinstance(body, dict) else None
            assert response.status == expected, (
                method,
                path,
                response.status,
                expected,
                code,
            )
            return body

    for client, email in zip(clients, accounts):
        call(client, "POST", "/auth/register/code", {"email": email})
        code = getpass("邮件中的六位验证码（隐藏输入）: ").strip()
        user = call(
            client,
            "POST",
            "/auth/register",
            {
                "email": email,
                "password": password,
                "confirm_password": password,
                "verification_code": code,
            },
            expected=201,
        )
        assert call(client, "GET", "/auth/me")["id"] == user["id"]
        assert call(client, "GET", "/todos")["items"] == []
    a, b = clients
    key = str(uuid4())
    payload = {"title": "  买牛奶  ", "description": "<b>纯文本</b>\n第二行"}
    todo = call(a, "POST", "/todos", payload, 201, {"Idempotency-Key": key})
    todo_id = todo["id"]
    assert todo["title"] == "买牛奶" and todo["due_date"] is None
    assert (
        call(a, "POST", "/todos", payload, 200, {"Idempotency-Key": key})["id"]
        == todo_id
    )
    call(a, "POST", "/todos", {"title": "不同内容"}, 409, {"Idempotency-Key": key})
    call(b, "GET", "/todos/" + todo_id, expected=404)
    call(b, "PATCH", "/todos/" + todo_id, {"status": "completed"}, 404)
    call(a, "PATCH", "/todos/" + todo_id, {"owner_id": str(uuid4())}, 422)
    call(
        a,
        "PATCH",
        "/todos/" + todo_id,
        {"title": "修改"},
        403,
        {"Origin": "https://example.invalid"},
    )
    edited = call(
        a, "PATCH", "/todos/" + todo_id, {"due_date": "2026-09-20", "due_time": "18:00"}
    )
    assert edited["due_at"] == "2026-09-20T10:00:00Z"
    cleared = call(a, "PATCH", "/todos/" + todo_id, {"due_date": None})
    assert cleared["due_time"] is None and cleared["due_at"] is None
    done = call(a, "PATCH", "/todos/" + todo_id, {"status": "completed"})
    twice = call(a, "PATCH", "/todos/" + todo_id, {"status": "completed"})
    assert done["completed_at"] == twice["completed_at"]
    assert call(a, "GET", "/todos?status=completed")["items"][0]["id"] == todo_id
    restored = call(a, "PATCH", "/todos/" + todo_id, {"status": "ongoing"})
    assert restored["completed_at"] is None
    call(a, "POST", "/auth/logout", expected=204)
    call(a, "GET", "/todos", expected=401)
    call(a, "POST", "/auth/logout", expected=204)
    call(a, "POST", "/auth/login", {"email": accounts[0], "password": password})
    assert call(a, "GET", "/todos/" + todo_id)["title"] == "买牛奶"
    assert call(b, "GET", "/todos")["items"] == []
    for client in clients:
        call(client, "POST", "/auth/logout", expected=204)
    print(
        "PASS: 真实注册/当前用户/幂等创建/双账号隔离/CSRF/编辑日期/完成恢复/退出重登持久化"
    )


if __name__ == "__main__":
    main()
