from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.api.calendar_schemas import EventCreate
from backend.api.document_schemas import ReviewPatch
from backend.api.hub_schemas import VoiceMemoConvert
from backend.api.life_schemas import MealCreate, ShoppingListCreate
from backend.api.planning_schemas import ChecklistCreate, ChecklistItemCreate
from backend.api.routes.life import create_meal
from backend.api.routes.life_edits import update_meal
from backend.api.schemas import TodoCreate, TodoPatch
from backend.db.household_models import HouseholdParticipant
from backend.db.life_models import MealPlan, ShoppingList
from backend.db.models import Checklist
from backend.db.sharing_models import ItemSharing, ItemSharingMember


@pytest.mark.parametrize(
    "model,extra",
    [
        (TodoCreate, {}),
        (TodoPatch, {}),
        (ChecklistCreate, {}),
        (ChecklistItemCreate, {}),
        (ReviewPatch, {}),
        (VoiceMemoConvert, {"target_type": "todo"}),
        (ShoppingListCreate, {}),
        (MealCreate, {"dish": "牛肉"}),
        (
            EventCreate,
            {
                "start_date": "2026-09-20",
                "end_date": "2026-09-20",
                "start_time": "18:00",
                "end_time": "19:00",
            },
        ),
    ],
)
def test_titles_allow_15_and_reject_16(model, extra):
    assert model(title="字" * 15, **extra).title == "字" * 15
    with pytest.raises(ValidationError):
        model(title="字" * 16, **extra)


def test_meal_title_defaults_and_can_be_edited():
    with pytest.raises(ValidationError):
        MealCreate(dish="牛肉", schedule_text="字" * 16)
    engine = create_engine("sqlite://")
    for model in (HouseholdParticipant, ItemSharing, ItemSharingMember):
        model.__table__.create(engine)
    for model in (Checklist, MealPlan, ShoppingList):
        model.__table__.create(engine)
    user = SimpleNamespace(id=uuid4(), timezone="Asia/Shanghai")
    with Session(engine) as session:
        meal = create_meal(MealCreate(dish="菜" * 20), user, session)
        assert meal.title == "餐食计划"
        assert meal.dish == "菜" * 20
        updated = update_meal(
            meal.id, MealCreate(schedule_text="周末晚餐", dish=meal.dish), user, session
        )
        assert updated.title == "周末晚餐"
        preserved = update_meal(
            meal.id, MealCreate(dish=meal.dish, date=date(2026, 9, 20)), user, session
        )
        assert preserved.title == "周末晚餐"
