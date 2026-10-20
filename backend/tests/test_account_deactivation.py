"""账号停用保留业务归属，同邮箱验证后恢复，旧会话永不恢复。"""

from helpers import PASSWORD, create, register, request_code


def test_deactivate_and_restore_retains_data_and_rejects_old_sessions(cloud):
    user, email = register(cloud)
    todo = create(cloud, title="恢复后仍可查看")
    old_token = cloud.cookies.get("session")
    assert cloud.delete("/api/auth/account").status_code == 204
    assert cloud.get("/api/auth/me").status_code == 401
    assert (
        cloud.post(
            "/api/auth/login", json={"email": email, "password": PASSWORD}
        ).status_code
        == 401
    )
    # 验证码错误不能激活旧数据。
    assert (
        cloud.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": PASSWORD,
                "confirm_password": PASSWORD,
                "verification_code": "000000",
            },
        ).status_code
        == 422
    )
    # 上次验证码已消费；测试邮箱冷却只清理专用命名空间中的单个键。
    from backend.core.security import redis
    from backend.features.auth.verification import keys

    redis.delete(keys(email, "")[1])
    new_password = "重新注册测试密码123456"
    result = cloud.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": new_password,
            "confirm_password": new_password,
            "verification_code": request_code(cloud, email),
        },
    )
    assert result.status_code == 201, result.text
    assert result.json()["id"] == user["id"]
    assert cloud.get(f"/api/todos/{todo['id']}").json()["title"] == "恢复后仍可查看"
    assert (
        cloud.get(
            "/api/auth/me", headers={"Cookie": f"session={old_token}"}
        ).status_code
        == 401
    )
    assert (
        cloud.post(
            "/api/auth/login", json={"email": email, "password": PASSWORD}
        ).status_code
        == 401
    )
    assert (
        cloud.post(
            "/api/auth/login", json={"email": email, "password": new_password}
        ).status_code
        == 200
    )
    assert cloud.delete("/api/auth/account", headers={"Cookie": ""}).status_code == 401
