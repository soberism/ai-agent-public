from helpers import register


def test_preferences_belong_to_meal_and_preserve_legacy_records(cloud):
    register(cloud)
    legacy = cloud.post(
        "/api/life/preferences", json={"label": "旧的少辣", "kind": "preference"}
    )
    assert legacy.status_code == 201
    body = {
        "date": "2026-09-20",
        "meal_type": "dinner",
        "diners": 2,
        "dish": "番茄炒蛋",
    }
    first = cloud.post(
        "/api/life/meal-plans",
        json={
            **body,
            "preferences": [
                {"label": "少盐", "kind": "preference"},
                {"label": "花生过敏", "kind": "allergy"},
                {"label": "50元以内", "kind": "budget"},
            ],
        },
    ).json()
    second = cloud.post("/api/life/meal-plans", json={**body, "dish": "牛肉面"}).json()
    assert len(first["preferences"]) == 3
    assert second["preferences"] == []
    assert first["shopping_url"]
    path = f"/api/life/meal-plans/{first['id']}"
    other_path = f"/api/life/meal-plans/{second['id']}"
    added = cloud.post(
        f"{path}/preferences", json={"label": " 少辣 ", "kind": "preference"}
    )
    assert added.status_code == 201, added.text
    preference_id = added.json()["preferences"][-1]["id"]
    assert added.json()["preferences"][-1]["label"] == "少辣"
    assert cloud.get(other_path).json()["preferences"] == []
    assert (
        cloud.post(
            f"{path}/preferences", json={"label": "少辣", "kind": "preference"}
        ).status_code
        == 409
    )
    assert (
        cloud.post(
            f"{path}/preferences", json={"label": "  ", "kind": "preference"}
        ).status_code
        == 422
    )
    assert cloud.delete(f"{other_path}/preferences/{preference_id}").status_code == 404
    assert cloud.put(path, json=body).status_code == 200
    assert len(cloud.get(path).json()["preferences"]) == 4
    removed = cloud.delete(f"{path}/preferences/{preference_id}")
    assert removed.status_code == 200
    assert len(removed.json()["preferences"]) == 3
    assert (
        cloud.get("/api/life/meal-plans").json()["preferences"][0]["id"]
        == legacy.json()["id"]
    )
    register(cloud)
    assert (
        cloud.post(
            f"{path}/preferences", json={"label": "清淡", "kind": "preference"}
        ).status_code
        == 404
    )
    assert (
        cloud.delete(f"{path}/preferences/{first['preferences'][0]['id']}").status_code
        == 404
    )
