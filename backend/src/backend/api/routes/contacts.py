from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import delete, func, or_, select

from backend.api.household_schemas import (
    ContactCreate,
    ContactList,
    ContactOut,
    GroupCreate,
    GroupList,
    GroupOut,
)
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal
from backend.db.household_models import Contact, ContactGroup, ContactGroupMembership
from backend.features.sharing.access import visible_condition
from backend.features.sharing.cleanup import delete_resource

router = APIRouter(tags=["联系人"], responses=ERROR_RESPONSES)


def contact_out(session, row, user):
    groups = session.scalars(
        select(ContactGroupMembership.group_id)
        .join(ContactGroup, ContactGroup.id == ContactGroupMembership.group_id)
        .where(
            visible_condition(ContactGroup, user.id),
            ContactGroupMembership.contact_id == row.id,
        )
    )
    return ContactOut(
        id=row.id,
        name=row.name,
        relationship=row.relationship,
        phone=row.phone,
        email=row.email,
        group_ids=list(groups),
    )


def owned_contact(session, user, contact_id):
    row = session.scalar(
        select(Contact).where(
            Contact.id == contact_id, visible_condition(Contact, user.id)
        )
    )
    if row is None:
        raise APIError(404, "CONTACT_NOT_FOUND", "联系人不存在或无法访问")
    return row


@router.get("/api/contacts", response_model=ContactList)
def contacts(
    user: Principal,
    session: DB,
    q: Annotated[str | None, Query(max_length=100)] = None,
):
    statement = select(Contact).where(visible_condition(Contact, user.id))
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                Contact.name.ilike(pattern),
                Contact.email.ilike(pattern),
                Contact.phone.ilike(pattern),
            )
        )
    rows = session.scalars(statement.order_by(Contact.name, Contact.id))
    return ContactList(items=[contact_out(session, row, user) for row in rows])


@router.post("/api/contacts", response_model=ContactOut, status_code=201)
def create_contact(body: ContactCreate, user: Principal, session: DB):
    if (body.email or body.phone) and session.scalar(
        select(Contact.id).where(
            visible_condition(Contact, user.id),
            or_(
                Contact.email == body.email if body.email else False,
                Contact.phone == body.phone if body.phone else False,
            ),
        )
    ):
        raise APIError(409, "CONTACT_DUPLICATE", "存在相同邮箱或电话的联系人，请先核对")
    row = Contact(owner_id=user.id, **body.model_dump())
    session.add(row)
    session.commit()
    return contact_out(session, row, user)


@router.patch("/api/contacts/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: UUID, body: ContactCreate, user: Principal, session: DB):
    row = owned_contact(session, user, contact_id)
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    session.commit()
    return contact_out(session, row, user)


@router.delete("/api/contacts/{contact_id}", status_code=204)
def remove_contact(contact_id: UUID, user: Principal, session: DB):
    delete_resource(session, owned_contact(session, user, contact_id))
    session.commit()


def group_out(session, row, user):
    ids = session.scalars(
        select(ContactGroupMembership.contact_id)
        .join(Contact, Contact.id == ContactGroupMembership.contact_id)
        .where(
            visible_condition(Contact, user.id),
            ContactGroupMembership.group_id == row.id,
        )
    )
    return GroupOut(id=row.id, name=row.name, contact_ids=list(ids))


@router.get("/api/contact-groups", response_model=GroupList)
def groups(user: Principal, session: DB):
    rows = session.scalars(
        select(ContactGroup)
        .where(visible_condition(ContactGroup, user.id))
        .order_by(ContactGroup.name, ContactGroup.id)
    )
    return GroupList(items=[group_out(session, row, user) for row in rows])


@router.post("/api/contact-groups", response_model=GroupOut, status_code=201)
def create_group(body: GroupCreate, user: Principal, session: DB):
    count = session.scalar(
        select(func.count()).where(
            visible_condition(Contact, user.id), Contact.id.in_(body.contact_ids)
        )
    )
    if count != len(set(body.contact_ids)):
        raise APIError(404, "CONTACT_NOT_FOUND", "部分联系人不存在或无法访问")
    row = ContactGroup(owner_id=user.id, name=body.name)
    session.add(row)
    session.flush()
    session.add_all(
        [
            ContactGroupMembership(group_id=row.id, contact_id=id)
            for id in body.contact_ids
        ]
    )
    session.commit()
    return group_out(session, row, user)


@router.put("/api/contact-groups/{group_id}", response_model=GroupOut)
def update_group(group_id: UUID, body: GroupCreate, user: Principal, session: DB):
    row = session.scalar(
        select(ContactGroup).where(
            ContactGroup.id == group_id, visible_condition(ContactGroup, user.id)
        )
    )
    if row is None:
        raise APIError(404, "GROUP_NOT_FOUND", "分组不存在或无法访问")
    contacts = list(
        session.scalars(
            select(Contact.id).where(
                visible_condition(Contact, user.id), Contact.id.in_(body.contact_ids)
            )
        )
    )
    if len(contacts) != len(set(body.contact_ids)):
        raise APIError(404, "CONTACT_NOT_FOUND", "部分联系人不存在或无法访问")
    row.name = body.name
    session.execute(
        delete(ContactGroupMembership).where(ContactGroupMembership.group_id == row.id)
    )
    session.add_all(
        [ContactGroupMembership(group_id=row.id, contact_id=id) for id in contacts]
    )
    session.commit()
    return group_out(session, row, user)


@router.delete("/api/contact-groups/{group_id}", status_code=204)
def remove_group(group_id: UUID, user: Principal, session: DB):
    row = session.scalar(
        select(ContactGroup).where(
            ContactGroup.id == group_id, visible_condition(ContactGroup, user.id)
        )
    )
    if row is None:
        raise APIError(404, "GROUP_NOT_FOUND", "分组不存在或无法访问")
    delete_resource(session, row)
    session.commit()
