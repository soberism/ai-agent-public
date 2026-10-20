from test_sharing_integration import family_accounts, login_as


def test_folder_visibility_follows_shared_files(cloud):
    _owner, own_cookie, home, member, member_cookie, _, _ = family_accounts(cloud)
    login_as(cloud, own_cookie)
    folder = cloud.post("/api/documents/folders", json={"name": "目录权限验证"}).json()
    files = []
    for name in ["共享.txt", "私有.txt"]:
        response = cloud.post(
            "/api/documents/materials",
            data={"folder_id": folder["id"]},
            files={"file": (name, name.encode(), "text/plain")},
            headers={"X-App-Request": "1"},
        )
        # multipart is accepted by the application's CSRF middleware.
        assert response.status_code == 201, response.text
        files.append(response.json())
    path = f"/api/sharing/material/{files[0]['id']}"
    assert (
        cloud.put(
            f"/api/sharing/folder/{folder['id']}",
            json={"scope": "household", "household_id": home["id"]},
        ).status_code
        == 404
    )
    login_as(cloud, member_cookie)
    assert cloud.get("/api/documents/materials").json()["folders"] == []
    login_as(cloud, own_cookie)
    assert (
        cloud.put(
            path,
            json={
                "scope": "members",
                "household_id": home["id"],
                "member_ids": [member["id"]],
            },
        ).status_code
        == 200
    )
    login_as(cloud, member_cookie)
    listing = cloud.get("/api/documents/materials").json()
    assert [f["id"] for f in listing["items"]] == [files[0]["id"]]
    assert listing["folders"] == [
        {"id": folder["id"], "name": folder["name"], "count": 1, "editable": False}
    ]
    assert cloud.delete(f"/api/documents/folders/{folder['id']}").status_code == 404
    assert (
        cloud.get(f"/api/documents/materials/{files[1]['id']}/content").status_code
        == 404
    )
    login_as(cloud, own_cookie)
    assert cloud.put(path, json={"scope": "private"}).status_code == 200
    login_as(cloud, member_cookie)
    assert cloud.get("/api/documents/materials").json()["folders"] == []
