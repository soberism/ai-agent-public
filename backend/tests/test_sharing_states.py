from helpers import create
from test_sharing_integration import family_accounts, login_as


def test_bulk_sharing_states_default_and_access_filter(cloud):
    _, cookies, home, member, member_cookie, _, _ = family_accounts(cloud)
    login_as(cloud, cookies)
    todos = [create(cloud, title=f"可见状态{i}") for i in range(3)]
    for todo, scope in zip(todos[1:], ("household", "members")):
        assert (
            cloud.put(
                f"/api/sharing/todo/{todo['id']}",
                json={
                    "scope": scope,
                    "household_id": home["id"],
                    "member_ids": [member["id"]],
                },
            ).status_code
            == 200
        )
    keys = [f"todo:{todo['id']}" for todo in todos]
    response = cloud.get("/api/sharing/states", params={"resources": ",".join(keys)})
    assert response.status_code == 200, response.text
    assert response.json()["states"] == dict(
        zip(keys, ("private", "household", "members"))
    )
    login_as(cloud, member_cookie)
    accessible = cloud.get(
        "/api/sharing/states", params={"resources": ",".join(keys)}
    ).json()["states"]
    assert (
        cloud.get("/api/sharing/states", params={"resources": ",".join(keys)}).json()[
            "editable"
        ]
        == []
    )
    for todo in todos[1:]:
        assert (
            cloud.put(
                f"/api/sharing/todo/{todo['id']}", json={"scope": "private"}
            ).status_code
            == 403
        )
    assert keys[0] not in accessible
    assert accessible == {keys[1]: "household", keys[2]: "members"}
    assert (
        cloud.get("/api/sharing/states", params={"resources": "invalid"}).status_code
        == 422
    )
    assert (
        cloud.get(
            "/api/sharing/states", params={"resources": ",".join([keys[0]] * 201)}
        ).status_code
        == 422
    )
