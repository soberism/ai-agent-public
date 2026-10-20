from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.api.life_schemas import MealCreate
from backend.api.routes.life import confirm_meal, create_meal, get_meal
from backend.api.routes.life_edits import update_meal
from backend.core.security import APIError
from backend.db.household_models import HouseholdParticipant
from backend.db.life_models import MealPlan, ShoppingList
from backend.db.models import CalendarEvent, Checklist
from backend.db.sharing_models import ItemSharing, ItemSharingMember


def test_date_without_meal_type_can_create_and_update_calendar_event():
    engine = create_engine("sqlite://")
    for model in (HouseholdParticipant, ItemSharing, ItemSharingMember):
        model.__table__.create(engine)
    for model in (Checklist, MealPlan, ShoppingList, CalendarEvent):
        model.__table__.create(engine)
    user = SimpleNamespace(id=uuid4(), timezone="Asia/Shanghai")
    with Session(engine) as session:
        meal = create_meal(
            MealCreate(dish="牛肉", date=date(2026, 9, 20), schedule_text="两人"),
            user,
            session,
        )
        planned = confirm_meal(meal.id, user, session)
        event = session.get(CalendarEvent, session.get(MealPlan, meal.id).event_id)
        assert event.starts_at.replace(tzinfo=UTC) == datetime(
            2026, 9, 20, 10, tzinfo=UTC
        )
        assert confirm_meal(meal.id, user, session).calendar_url == planned.calendar_url
        update_meal(
            meal.id,
            MealCreate(dish="牛肉", date=date(2026, 9, 21), schedule_text="两人"),
            user,
            session,
        )
        assert event.starts_at.replace(tzinfo=UTC) == datetime(
            2026, 9, 21, 10, tzinfo=UTC
        )


def test_free_text_is_persistent_and_does_not_invent_time_or_people():
    engine = create_engine("sqlite://")
    for model in (HouseholdParticipant, ItemSharing, ItemSharingMember):
        model.__table__.create(engine)
    Checklist.__table__.create(engine)
    MealPlan.__table__.create(engine)
    ShoppingList.__table__.create(engine)
    user = SimpleNamespace(id=uuid4(), timezone="Asia/Shanghai")
    with Session(engine) as session:
        text = "周末吃，两三个人 🌧️"
        result = create_meal(MealCreate(dish="牛肉", schedule_text=text), user, session)
        session.expire_all()
        loaded = get_meal(result.id, user, session)
        assert loaded.schedule_text == text
        assert loaded.date is loaded.meal_type is loaded.diners is None
        assert loaded.shopping_url is not None
        with pytest.raises(APIError) as error:
            confirm_meal(result.id, user, session)
        assert error.value.status == 422


def test_free_text_api_in_cloud_test_database(cloud):
    from helpers import register

    register(cloud)
    text = "随便什么时候吃，两三个人都行"
    result = cloud.post(
        "/api/life/meal-plans", json={"dish": "牛肉", "schedule_text": text}
    )
    assert result.status_code == 201
    row = result.json()
    loaded = cloud.get(f"/api/life/meal-plans/{row['id']}").json()
    assert loaded["schedule_text"] == text
    assert loaded["date"] is loaded["meal_type"] is loaded["diners"] is None
    assert (
        cloud.get(
            f"/api/planning/checklists/{row['shopping_url'].split('/')[-1]}"
        ).status_code
        == 200
    )
    assert (
        cloud.post(f"/api/life/meal-plans/{row['id']}/confirm", json={}).status_code
        == 422
    )
