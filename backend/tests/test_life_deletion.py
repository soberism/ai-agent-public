from helpers import register


def test_delete_meal_and_shopping_preserves_related_records(cloud):
    register(cloud)
    body = {"date": "2026-09-20", "meal_type": "dinner", "diners": 2, "dish": "面条"}
    meal = cloud.post("/api/life/meal-plans", json=body).json()
    meal_path = f"/api/life/meal-plans/{meal['id']}"
    shopping_path = f"/api/life/shopping-lists/{meal['shopping_url'].split('/')[-1]}"
    added = cloud.post(f"{shopping_path}/items", json={"name": "鸡蛋", "quantity": 2})
    assert added.status_code == 201
    assert added.json()["items"][0]["unit"] == ""
    assert added.json()["items"][0]["category"] == ""
    assert cloud.delete(shopping_path).status_code == 204
    assert cloud.get(meal_path).json()["shopping_url"] is None
    assert cloud.delete(shopping_path).status_code == 404
    second = cloud.post("/api/life/meal-plans", json=body).json()
    second_path = f"/api/life/meal-plans/{second['id']}"
    second_shopping = (
        f"/api/life/shopping-lists/{second['shopping_url'].split('/')[-1]}"
    )
    calendar = cloud.post(f"{second_path}/confirm", json={}).json()["calendar_url"]
    assert cloud.delete(second_path).status_code == 204
    assert cloud.get(second_shopping).json()["meal_id"] is None
    assert (
        cloud.get(f"/api/calendar/events/{calendar.split('/')[-2]}").status_code == 200
    )
    assert cloud.delete(second_path).status_code == 404
    register(cloud)
    assert cloud.delete(meal_path).status_code == 404
    assert cloud.delete(second_shopping).status_code == 404
