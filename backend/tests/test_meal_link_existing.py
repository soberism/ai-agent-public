from helpers import register


def test_link_existing_shopping_list(cloud):
    register(cloud)
    shopping = cloud.post("/api/life/shopping-lists", json={"title": "周末采购"}).json()
    path = f"/api/life/shopping-lists/{shopping['id']}"
    cloud.post(f"{path}/items", json={"name": "鸡蛋", "quantity": 2})
    body = {
        "date": "2026-09-20",
        "meal_type": "dinner",
        "diners": 2,
        "dish": "炒蛋",
        "shopping_list_id": shopping["id"],
    }
    result = cloud.post("/api/life/meal-plans", json=body)
    assert result.status_code == 201, result.text
    assert result.json()["shopping_url"] == shopping["checklist_url"]
    linked = cloud.get(path).json()
    assert linked["meal_id"] == result.json()["id"]
    assert linked["title"] == "周末采购"
    assert linked["items"][0]["name"] == "鸡蛋 2"
    assert len(cloud.get("/api/life/shopping-lists/overview").json()["items"]) == 1
    assert cloud.post("/api/life/meal-plans", json=body).status_code == 409
    assert len(cloud.get("/api/life/meal-plans").json()["items"]) == 1
    register(cloud)
    assert cloud.post("/api/life/meal-plans", json=body).status_code == 404
    assert cloud.get("/api/life/meal-plans").json()["items"] == []
