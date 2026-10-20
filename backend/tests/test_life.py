from helpers import register


def test_life_planning_and_confirmed_plan_links(cloud):
    register(cloud)
    assert cloud.get("/api/life/capabilities").json() == {
        "delivery": False,
        "payment": False,
        "medical_booking": False,
    }
    preference = cloud.post(
        "/api/life/preferences", json={"label": "不吃花生", "kind": "allergy"}
    )
    assert preference.status_code == 201
    pantry = cloud.post(
        "/api/life/pantry", json={"name": "牛奶", "quantity": 2, "unit": "盒"}
    )
    assert pantry.status_code == 201
    for body in (
        {"name": "鸡蛋", "quantity": 2},
        {"name": "番茄", "quantity": 3, "unit": ""},
    ):
        optional_unit = cloud.post("/api/life/pantry", json=body)
        assert optional_unit.status_code == 201, optional_unit.text
        assert optional_unit.json()["unit"] == ""
    meal = cloud.post(
        "/api/life/meal-plans",
        json={
            "date": "2026-10-08",
            "meal_type": "dinner",
            "diners": 3,
            "dish": "番茄牛腩",
            "notes": "少盐",
        },
    ).json()
    confirmed_meal = cloud.post(f"/api/life/meal-plans/{meal['id']}/confirm", json={})
    assert confirmed_meal.status_code == 200
    assert confirmed_meal.json()["calendar_url"].endswith("/edit")
    overview = cloud.get("/api/life/meal-plans").json()
    assert overview["items"][0]["diners"] == 3
    assert overview["preferences"][0]["label"] == "不吃花生"

    empty_list = cloud.get("/api/life/shopping-lists").json()
    assert empty_list["items"] == []
    shopping = cloud.post(
        "/api/life/shopping-lists/items",
        json={"name": "番茄", "quantity": 3, "unit": "个", "category": "蔬菜"},
    ).json()
    item_id = shopping["items"][0]["id"]
    checked = cloud.patch(
        f"/api/life/shopping-lists/items/{item_id}", json={"purchased": True}
    )
    assert checked.json()["items"][0]["purchased"] is True
    confirmed_list = cloud.post("/api/life/shopping-lists/confirm", json={})
    assert confirmed_list.json()["checklist_url"].startswith("/checklists/")

    appointment = cloud.post(
        "/api/life/appointments",
        json={
            "patient_name": "小明",
            "institution": "社区医院",
            "service_type": "常规复查",
            "preferred_at": "2026-10-09T09:30:00+08:00",
            "fee_note": "费用以医院为准",
        },
    )
    assert appointment.status_code == 201
    assert appointment.json()["status"] == "planned"
    assert appointment.json()["external_receipt"] is None
    linked = cloud.post(
        f"/api/life/appointments/{appointment.json()['id']}/confirm", json={}
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["calendar_url"] and linked.json()["todo_url"]
    replay = cloud.post(
        f"/api/life/appointments/{appointment.json()['id']}/confirm", json={}
    )
    assert replay.json()["calendar_url"] == linked.json()["calendar_url"]
