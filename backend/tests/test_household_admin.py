from helpers import register
from test_households import login


def test_admin_member_management_boundary(cloud):
    _, owner = register(cloud)
    cloud.post("/api/auth/logout", json={})
    _, admin = register(cloud)
    cloud.post("/api/auth/logout", json={})
    _, member = register(cloud)
    cloud.post("/api/auth/logout", json={})
    login(cloud, owner)
    home = cloud.post("/api/households", json={"name": "权限测试"}).json()
    base = f"/api/households/{home['id']}"
    invitation = cloud.post(base + "/invitations", json={"email": admin}).json()
    cloud.post("/api/auth/logout", json={})
    login(cloud, admin)
    assert (
        cloud.post(
            f"/api/households/invitations/{invitation['id']}/accept", json={}
        ).status_code
        == 200
    )
    assert cloud.post(base + "/invitations", json={"email": member}).status_code == 404
    cloud.post("/api/auth/logout", json={})
    login(cloud, owner)
    assert (
        cloud.patch(
            base + f"/members/{invitation['id']}", json={"role": "admin"}
        ).status_code
        == 200
    )
    owner_id = next(
        x["id"] for x in cloud.get(base).json()["members"] if x["role"] == "owner"
    )
    cloud.post("/api/auth/logout", json={})
    login(cloud, admin)
    invited = cloud.post(base + "/invitations", json={"email": member})
    assert invited.status_code == 201, invited.text
    target = base + f"/members/{invited.json()['id']}"
    for body in (
        {"role": "admin"},
        {"permissions": []},
        {"status": "active"},
        {"status": "removed", "role": "admin"},
        {"role": None},
    ):
        assert cloud.patch(target, json=body).status_code == 404
    assert cloud.delete(base).status_code == 404
    assert (
        cloud.patch(
            base + f"/members/{owner_id}", json={"status": "removed"}
        ).status_code
        == 404
    )
    cloud.post("/api/auth/logout", json={})
    login(cloud, member)
    assert (
        cloud.post(
            f"/api/households/invitations/{invited.json()['id']}/accept", json={}
        ).status_code
        == 200
    )
    assert (
        cloud.get(base + f"/members/{invitation['id']}/removal-impact").status_code
        == 404
    )
    assert (
        cloud.patch(
            base + f"/members/{invitation['id']}", json={"status": "removed"}
        ).status_code
        == 404
    )
    cloud.post("/api/auth/logout", json={})
    login(cloud, admin)
    assert cloud.get(target + "/removal-impact").status_code == 200
    assert cloud.patch(target, json={"status": "removed"}).status_code == 200
    cloud.post("/api/auth/logout", json={})
    login(cloud, member)
    assert cloud.get(base).status_code == 404
