import pytest
from helpers import register
from test_sharing_integration import family_accounts, login_as


@pytest.mark.parametrize("decision", ["accept", "reject"])
def test_invitation_decision_notifies_sender_and_clears_recipient(cloud, decision):
    _, owner_cookie, home, _, _, _, _ = family_accounts(cloud)
    cloud.cookies.clear()
    _, email = register(cloud)
    receiver_cookie = dict(cloud.cookies)
    login_as(cloud, owner_cookie)
    invitation = cloud.post(
        f"/api/households/{home['id']}/invitations",
        json={"email": email, "role": "member"},
    ).json()
    login_as(cloud, receiver_cookie)
    incoming = cloud.get("/api/households/invitations/incoming").json()["items"]
    assert any(item["id"] == invitation["id"] for item in incoming)
    result = cloud.post(
        f"/api/households/invitations/{invitation['id']}/{decision}", json={}
    )
    assert result.status_code == 200, result.text
    assert cloud.get("/api/households/invitations/incoming").json()["items"] == []
    notices = cloud.get("/api/notifications").json()["items"]
    assert all(
        item["read"] for item in notices if item["invitation_id"] == invitation["id"]
    )
    # Repeated decisions cannot emit a second feedback notification.
    assert (
        cloud.post(
            f"/api/households/invitations/{invitation['id']}/{decision}", json={}
        ).status_code
        == 404
    )
    login_as(cloud, owner_cookie)
    feedback = [
        item
        for item in cloud.get("/api/notifications").json()["items"]
        if item["invitation_id"] == invitation["id"]
    ]
    assert len(feedback) == 1
    assert feedback[0]["type"] == "invitation_result"
    assert not feedback[0]["read"]
    assert ("已接受" if decision == "accept" else "已拒绝") in feedback[0]["message"]
    login_as(cloud, receiver_cookie)
    assert (
        cloud.post(f"/api/notifications/{feedback[0]['id']}/read", json={}).status_code
        == 404
    )
    login_as(cloud, owner_cookie)
    assert cloud.post(f"/api/notifications/{feedback[0]['id']}/read", json={}).json()[
        "read"
    ]
