"""Schema and registry tests for the focused person relation tools.

End-to-end SQL coverage requires Postgres + pg_trgm (see
`tests/integration/` once that lands). This unit suite locks the input
validation, registry wiring, and statement-builder branches that determine
which join shape goes to the database for each `relation`."""

from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.sql import ColumnElement

from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.tools.persons import (
    PersonCountRelationsInput,
    PersonRelationsInput,
    _relations_stmt,
)
from my_family_tree.models.enums import PersonStatus, RelType
from my_family_tree.models.person import Person
from my_family_tree.models.relationship import Relationship


@pytest.mark.unit
def test_relations_tools_registered_as_read() -> None:
    registry = get_registry()
    for name in ("person_relations", "person_count_relations"):
        tool = registry.get(name)
        assert tool.capability & Capability.READ, f"{name} should be READ"
        assert tool.is_read_only is True


@pytest.mark.unit
def test_relations_input_rejects_unknown_relation() -> None:
    with pytest.raises(PydanticValidationError):
        PersonRelationsInput(person_id=uuid4(), relation="cousins")  # type: ignore[arg-type]


@pytest.mark.unit
def test_relations_input_rejects_unknown_sex_filter() -> None:
    with pytest.raises(PydanticValidationError):
        PersonRelationsInput(
            person_id=uuid4(),
            relation="children",
            sex_filter="nonbinary",  # type: ignore[arg-type]
        )


@pytest.mark.unit
def test_relations_input_clamps_limit_range() -> None:
    PersonRelationsInput(person_id=uuid4(), relation="children", limit=1)
    PersonRelationsInput(person_id=uuid4(), relation="children", limit=200)
    with pytest.raises(PydanticValidationError):
        PersonRelationsInput(person_id=uuid4(), relation="children", limit=0)
    with pytest.raises(PydanticValidationError):
        PersonRelationsInput(person_id=uuid4(), relation="children", limit=201)


@pytest.mark.unit
def test_count_input_only_requires_person_id() -> None:
    payload = PersonCountRelationsInput(person_id=uuid4())
    assert payload.person_id is not None


@pytest.mark.unit
def test_relations_stmt_children_joins_on_object_id() -> None:
    """Children of `root` are objects of `parent_of` edges where the subject
    is `root`. Compile the SQL string and verify the right column predicates
    show up so a future refactor can't silently flip the join direction."""
    root = uuid4()
    tree = uuid4()
    sql = _compile(_relations_stmt(root, "children", tree))
    assert "relationship.subject_id = " in sql
    assert "relationship.type = 'parent_of'" in sql
    assert "person.status = 'active'" in sql


@pytest.mark.unit
def test_relations_stmt_parents_joins_on_subject_id() -> None:
    root = uuid4()
    tree = uuid4()
    sql = _compile(_relations_stmt(root, "parents", tree))
    assert "relationship.object_id = " in sql
    assert "relationship.type = 'parent_of'" in sql


@pytest.mark.unit
def test_relations_stmt_spouses_uses_spouse_of() -> None:
    root = uuid4()
    tree = uuid4()
    sql = _compile(_relations_stmt(root, "spouses", tree))
    assert "relationship.type = 'spouse_of'" in sql
    assert "relationship.subject_id = " in sql


@pytest.mark.unit
def test_relations_stmt_siblings_uses_shared_parents_subquery() -> None:
    """The sibling case derives kin from a shared `parent_of` edge so a tree
    that only stores parent edges still surfaces siblings without an
    explicit `sibling_of` row."""
    root = uuid4()
    tree = uuid4()
    sql = _compile(_relations_stmt(root, "siblings", tree))
    # The IN subselect against parent_of subjects is the giveaway.
    assert sql.count("'parent_of'") >= 2
    assert "person.id != " in sql or "person.id <> " in sql


@pytest.mark.unit
def test_relations_stmt_filters_active_persons_only() -> None:
    root = uuid4()
    tree = uuid4()
    for relation in ("children", "parents", "siblings", "spouses"):
        sql = _compile(_relations_stmt(root, relation, tree))  # type: ignore[arg-type]
        assert "person.status = 'active'" in sql, f"{relation} did not filter status"


def _compile(stmt: object) -> str:
    """Compile a SQLAlchemy `Select` to a literal-bound SQL string. We only
    look at predicate shape, so a postgres-flavored compile is unnecessary."""
    compiled = cast(ColumnElement[object], stmt).compile(compile_kwargs={"literal_binds": True})
    return str(compiled).replace("\n", " ")


# Touch unused imports so ruff does not warn.
_ = (Person, Relationship, RelType, PersonStatus, UUID, select)
