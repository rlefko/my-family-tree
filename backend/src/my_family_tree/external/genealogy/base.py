"""Provider-neutral types for genealogy lookups.

Each provider returns rows shaped like `GenealogyHit` from search and a
`GenealogyProfile` (with related persons grouped by relation kind) from
get-by-id. Birth and death dates are stringly-typed because external
sources don't agree on precision (years only, ranges, calendar systems);
parsing happens later if a proposal is created from the result."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, cast


def as_dict(value: object) -> dict[str, Any] | None:
    """Return `value` as a `dict[str, Any]` if it's a dict, else None.

    Used by providers to traverse JSON without having to fight ty's strict
    invariant-generic narrowing. The `cast` is safe because we just verified
    via `isinstance` that the runtime type is `dict`."""
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return None


def as_list(value: object) -> list[Any] | None:
    if isinstance(value, list):
        return cast(list[Any], value)
    return None


def split_query_name(query: str) -> tuple[str, str]:
    """Best-effort `(first_names, last_name)` split for provider search inputs.

    Everything up to the last whitespace-separated token is treated as the
    given name(s); the last token becomes the surname. A single-token query
    is treated as a surname so providers return broader matches."""
    parts = query.strip().split()
    if not parts:
        return ("", "")
    if len(parts) == 1:
        return ("", parts[0])
    return (" ".join(parts[:-1]), parts[-1])


@dataclass(slots=True, frozen=True)
class GenealogyHit:
    provider: str
    provider_id: str
    name: str
    summary: str
    url: str | None
    birth: str | None
    death: str | None
    place: str | None
    score: float


@dataclass(slots=True, frozen=True)
class GenealogyRelative:
    provider: str
    provider_id: str | None
    relation: str
    name: str
    url: str | None = None
    birth: str | None = None
    death: str | None = None


@dataclass(slots=True, frozen=True)
class GenealogyProfile:
    provider: str
    provider_id: str
    name: str
    summary: str
    url: str | None
    birth: str | None
    death: str | None
    birth_place: str | None
    death_place: str | None
    relatives: list[GenealogyRelative] = field(default_factory=list)
    raw: dict | None = None


class GenealogyProvider(Protocol):
    name: str

    async def search(
        self,
        query: str,
        *,
        k: int,
        birth_year: int | None = None,
        death_year: int | None = None,
        place: str | None = None,
    ) -> list[GenealogyHit]: ...

    async def get_person(self, provider_id: str) -> GenealogyProfile: ...

    async def aclose(self) -> None: ...
