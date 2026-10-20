from helpers import register


def test_material_dedup_review_and_real_event_creation(cloud):
    register(cloud)
    folder = cloud.post("/api/documents/folders", json={"name": "学校"}).json()
    content = "秋季家长会 2026年10月8日 19:00\n请准时参加".encode()
    uploaded = cloud.post(
        "/api/documents/materials",
        data={"folder_id": folder["id"], "recognize": "true"},
        files={"file": ("notice.txt", content, "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    material = uploaded.json()
    assert material["status"] == "ready" and material["review_count"] == 1
    assert cloud.get("/api/documents/materials").json()["folders"][0]["count"] == 1
    original = cloud.get(f"/api/documents/materials/{material['id']}/content")
    assert original.content == content and original.headers["content-type"].startswith(
        "text/plain"
    )

    pending = cloud.get(
        "/api/documents/review-items", params={"status": "pending"}
    ).json()["items"]
    item = pending[0]
    assert item["material_id"] == material["id"] and item["target_type"] == "event"
    changed = cloud.patch(
        f"/api/documents/review-items/{item['id']}", json={"title": "家长会"}
    )
    assert changed.status_code == 200
    accepted = cloud.post(f"/api/documents/review-items/{item['id']}/accept", json={})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["target_url"].endswith("/edit")
    replay = cloud.post(f"/api/documents/review-items/{item['id']}/accept", json={})
    assert replay.json()["target_url"] == accepted.json()["target_url"]
    events = cloud.get(
        "/api/calendar/events",
        params={"date_from": "2026-10-08", "date_to": "2026-10-08"},
    ).json()["items"]
    assert events[0]["title"] == "家长会" and events[0]["source"] == "document"

    duplicate = cloud.post(
        "/api/documents/materials",
        files={"file": ("copy.txt", content, "text/plain")},
    )
    assert duplicate.status_code == 409
    assert cloud.get("/api/documents/capabilities").json()["email"] is False


def test_file_management_without_recognition(cloud):
    register(cloud)
    uploaded = cloud.post(
        "/api/documents/materials",
        files={"file": ("notice.txt", "会议2026年10月8日19:00".encode(), "text/plain")},
    )
    assert uploaded.status_code == 201
    item = uploaded.json()
    assert item["status"] == "uploaded" and item["review_count"] == 0
    assert item["error_message"] is None
    url = f"/api/documents/materials/{item['id']}"
    assert cloud.patch(url, json={"name": "新文件.txt"}).json()["name"] == "新文件.txt"
    assert cloud.patch(url, json={"name": "../bad"}).status_code == 422
    assert (
        cloud.get(url + "/download")
        .headers["content-disposition"]
        .startswith("attachment")
    )
    assert cloud.delete(url).status_code == 204
    assert cloud.get(url + "/content").status_code == 404


def test_file_size_limit_20_mib(cloud):
    register(cloud)
    size = 20 * 1024 * 1024
    uploaded = cloud.post(
        "/api/documents/materials",
        files={"file": ("limit.bin", b"x" * size, "application/octet-stream")},
    )
    assert uploaded.status_code == 201, uploaded.text
    rejected = cloud.post(
        "/api/documents/materials",
        files={
            "file": ("too-large.bin", b"x" * (size + 1), "application/octet-stream")
        },
    )
    assert rejected.status_code == 413
    assert (
        cloud.delete(f"/api/documents/materials/{uploaded.json()['id']}").status_code
        == 204
    )


def test_duplicate_directory_returns_clear_error_repeatedly(cloud):
    register(cloud)
    assert (
        cloud.post("/api/documents/folders", json={"name": "资料"}).status_code == 201
    )
    for _ in range(2):
        response = cloud.post("/api/documents/folders", json={"name": "资料"})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "FOLDER_DUPLICATE"
    assert cloud.get("/api/documents/materials").status_code == 200


def test_remove_directory_keeps_files(cloud):
    register(cloud)
    folder = cloud.post("/api/documents/folders", json={"name": "目录"}).json()
    item = cloud.post(
        "/api/documents/materials",
        data={"folder_id": folder["id"]},
        files={"file": ("file.txt", b"retained", "text/plain")},
    ).json()
    assert cloud.delete(f"/api/documents/folders/{folder['id']}").status_code == 204
    listing = cloud.get("/api/documents/materials").json()
    assert listing["items"][0]["folder_id"] is None
    assert listing["folders"] == []
    assert (
        cloud.get(f"/api/documents/materials/{item['id']}/content").content
        == b"retained"
    )
