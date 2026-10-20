from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select

from backend.api.household_schemas import PetCreate, PetOut, ProfileCreate, ProfileOut
from backend.api.routes.households import participant
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal
from backend.db.household_models import HouseholdProfile, Pet
from backend.features.sharing.cleanup import delete_resource

router = APIRouter(prefix="/api/households", tags=["家庭"], responses=ERROR_RESPONSES)


def owned(session, model, household_id, object_id, code):
    row = session.scalar(
        select(model).where(model.id == object_id, model.household_id == household_id)
    )
    if row is None:
        raise APIError(404, code, "对象不存在或无法访问")
    return row


@router.post("/{household_id}/profiles", response_model=ProfileOut, status_code=201)
def create_profile(
    household_id: UUID, body: ProfileCreate, user: Principal, session: DB
):
    participant(session, user, household_id, manage=True)
    row = HouseholdProfile(household_id=household_id, **body.model_dump())
    session.add(row)
    session.commit()
    return ProfileOut.model_validate(row, from_attributes=True)


@router.put("/{household_id}/profiles/{profile_id}", response_model=ProfileOut)
def update_profile(
    household_id: UUID,
    profile_id: UUID,
    body: ProfileCreate,
    user: Principal,
    session: DB,
):
    participant(session, user, household_id, manage=True)
    row = owned(
        session, HouseholdProfile, household_id, profile_id, "PROFILE_NOT_FOUND"
    )
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    session.commit()
    return ProfileOut.model_validate(row, from_attributes=True)


@router.delete("/{household_id}/profiles/{profile_id}", status_code=204)
def delete_profile(household_id: UUID, profile_id: UUID, user: Principal, session: DB):
    participant(session, user, household_id, manage=True)
    delete_resource(
        session,
        owned(session, HouseholdProfile, household_id, profile_id, "PROFILE_NOT_FOUND"),
    )
    session.commit()


@router.post("/{household_id}/pets", response_model=PetOut, status_code=201)
def create_pet(household_id: UUID, body: PetCreate, user: Principal, session: DB):
    participant(session, user, household_id, manage=True)
    row = Pet(household_id=household_id, **body.model_dump())
    session.add(row)
    session.commit()
    return PetOut.model_validate(row, from_attributes=True)


@router.put("/{household_id}/pets/{pet_id}", response_model=PetOut)
def update_pet(
    household_id: UUID,
    pet_id: UUID,
    body: PetCreate,
    user: Principal,
    session: DB,
):
    participant(session, user, household_id, manage=True)
    row = owned(session, Pet, household_id, pet_id, "PET_NOT_FOUND")
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    session.commit()
    return PetOut.model_validate(row, from_attributes=True)


@router.delete("/{household_id}/pets/{pet_id}", status_code=204)
def delete_pet(household_id: UUID, pet_id: UUID, user: Principal, session: DB):
    participant(session, user, household_id, manage=True)
    delete_resource(session, owned(session, Pet, household_id, pet_id, "PET_NOT_FOUND"))
    session.commit()
