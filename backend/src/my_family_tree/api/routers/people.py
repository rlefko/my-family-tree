"""People endpoints: list, get, search."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import or_, select

from my_family_tree.api.deps import SessionDep
from my_family_tree.core.errors import NotFoundError
from my_family_tree.models.enums import PersonStatus
from my_family_tree.models.person import Person

router = APIRouter()


class PersonRow(BaseModel):
    id: UUID
    display_name: str
    sex: str
    surname: str | None = None
    given_names: str | None = None


class PeopleList(BaseModel):
    items: list[PersonRow]


@router.get("/people", response_model=PeopleList)
async def list_people(
    session: SessionDep,
    q: str | None = None,
    limit: int = 50,
) -> PeopleList:
    stmt = select(Person).where(Person.status == PersonStatus.active)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Person.display_name.ilike(like),
                Person.surname.ilike(like),
                Person.given_names.ilike(like),
            )
        )
    stmt = stmt.order_by(Person.display_name.asc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return PeopleList(
        items=[
            PersonRow(
                id=p.id,
                display_name=p.display_name,
                sex=p.sex.value,
                surname=p.surname,
                given_names=p.given_names,
            )
            for p in rows
        ]
    )


@router.get("/people/{person_id}", response_model=PersonRow)
async def get_person(person_id: UUID, session: SessionDep) -> PersonRow:
    person = await session.get(Person, person_id)
    if person is None:
        raise NotFoundError(f"person {person_id} not found")
    return PersonRow(
        id=person.id,
        display_name=person.display_name,
        sex=person.sex.value,
        surname=person.surname,
        given_names=person.given_names,
    )
