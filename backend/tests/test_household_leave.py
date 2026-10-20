from helpers import create
from test_sharing_integration import family_accounts, login_as


def test_member_can_leave_and_both_sides_lose_shared_access(cloud):
    _, owner_cookie, home, _, member_cookie, _, _ = family_accounts(cloud)
    login_as(cloud, owner_cookie)
    owner_todo = create(cloud, title="家庭共享")
    assert (
        cloud.put(
            f"/api/sharing/todo/{owner_todo['id']}",
            json={"scope": "household", "household_id": home["id"]},
        ).status_code
        == 200
    )
    assert cloud.post(f"/api/households/{home['id']}/leave", json={}).status_code == 409
    login_as(cloud, member_cookie)
    member_todo = create(cloud, title="成员保留")
    assert (
        cloud.put(
            f"/api/sharing/todo/{member_todo['id']}",
            json={"scope": "household", "household_id": home["id"]},
        ).status_code
        == 200
    )
    assert cloud.get(f"/api/todos/{owner_todo['id']}").status_code == 200
    assert cloud.post(f"/api/households/{home['id']}/leave", json={}).status_code == 204
    assert cloud.post(f"/api/households/{home['id']}/leave", json={}).status_code == 404
    assert cloud.get("/api/households").json()["items"] == []
    assert cloud.get(f"/api/todos/{owner_todo['id']}").status_code == 404
    assert cloud.get(f"/api/todos/{member_todo['id']}").status_code == 200
    login_as(cloud, owner_cookie)
    assert cloud.get(f"/api/households/{home['id']}").json()["member_count"] == 2
    assert cloud.get(f"/api/todos/{member_todo['id']}").status_code == 404
