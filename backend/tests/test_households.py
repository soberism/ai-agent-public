from helpers import PASSWORD, register


def login(client, email):
    result = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert result.status_code == 200, result.text


def test_household_invitation_permissions_contacts_and_notifications(cloud):
    _, owner_email = register(cloud)
    assert cloud.post("/api/auth/logout").status_code == 204
    _, helper_email = register(cloud)
    assert cloud.post("/api/auth/logout").status_code == 204
    login(cloud, owner_email)

    home = cloud.post("/api/households", json={"name": "周末之家"}).json()
    invitation = cloud.post(
        f"/api/households/{home['id']}/invitations",
        json={"email": helper_email, "role": "member"},
    )
    assert invitation.status_code == 201, invitation.text
    invitation = invitation.json()

    profile = cloud.post(
        f"/api/households/{home['id']}/profiles",
        json={"name": "小明", "relationship": "孩子", "birth_date": "2018-05-06"},
    )
    assert profile.status_code == 201
    pet = cloud.post(
        f"/api/households/{home['id']}/pets",
        json={"name": "团子", "species": "猫", "breed": "狸花"},
    )
    assert pet.status_code == 201

    contact = cloud.post(
        "/api/contacts",
        json={"name": "王老师", "relationship": "老师", "phone": "13800000000"},
    ).json()
    group = cloud.post(
        "/api/contact-groups",
        json={"name": "学校", "contact_ids": [contact["id"]]},
    )
    assert group.status_code == 201
    assert group.json()["contact_ids"] == [contact["id"]]

    assert cloud.post("/api/auth/logout").status_code == 204
    login(cloud, helper_email)
    notices = cloud.get("/api/notifications").json()["items"]
    assert notices[0]["invitation_id"] == invitation["id"]
    assert notices[0]["read"] is False
    accepted = cloud.post(
        f"/api/households/invitations/{invitation['id']}/accept", json={}
    )
    assert accepted.status_code == 200
    detail = cloud.get(f"/api/households/{home['id']}").json()
    assert len(detail["profiles"]) == 1 and len(detail["pets"]) == 1
    assert cloud.get("/api/contacts").json()["items"] == []

    assert cloud.post("/api/auth/logout").status_code == 204
    login(cloud, owner_email)
    member_id = next(
        item["id"]
        for item in cloud.get(f"/api/households/{home['id']}").json()["members"]
        if item["email"] == helper_email
    )
    updated = cloud.patch(
        f"/api/households/{home['id']}/members/{member_id}",
        json={"permissions": ["calendar_read", "document_read"]},
    )
    assert updated.status_code == 200
    removed = cloud.patch(
        f"/api/households/{home['id']}/members/{member_id}",
        json={"status": "removed"},
    )
    assert removed.status_code == 200
    assert cloud.post("/api/auth/logout").status_code == 204
    login(cloud, helper_email)
    assert cloud.get(f"/api/households/{home['id']}").status_code == 404

    assert cloud.post("/api/auth/logout").status_code == 204
    login(cloud, owner_email)
    renewed = cloud.post(
        f"/api/households/{home['id']}/invitations",
        json={"email": helper_email, "role": "member"},
    )
    assert renewed.status_code == 201, renewed.text
    assert cloud.post("/api/auth/logout").status_code == 204
    login(cloud, helper_email)
    assert (
        cloud.post(
            f"/api/households/invitations/{renewed.json()['id']}/accept", json={}
        ).status_code
        == 200
    )
