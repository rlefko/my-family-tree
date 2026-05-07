"""WikiTree REST provider. https://github.com/wikitree/wikitree-api

WikiTree is the largest single shared genealogy tree on the public web.
Public profiles are accessible without auth as long as the request carries
a descriptive `User-Agent`, which the project's settings supply. We only
return profiles with `Privacy_IsPublic == 1` so private trees are never
echoed into our knowledge base."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from my_family_tree.core.errors import ExternalProviderError
from my_family_tree.external.genealogy.base import (
    GenealogyHit,
    GenealogyProfile,
    GenealogyProvider,
    GenealogyRelative,
    as_dict,
    as_list,
)
from my_family_tree.external.http import build_http_client, request_json

WIKITREE_API_URL = "https://api.wikitree.com/api.php"

# Fields to request from WikiTree. Keep it tight: any field we don't ship
# back to the agent is wasted bandwidth and an extra surface for PII.
PROFILE_FIELDS = (
    "Id,Name,FirstName,MiddleName,LastNameAtBirth,LastNameCurrent,"
    "BirthDate,DeathDate,BirthLocation,DeathLocation,IsLiving,"
    "Privacy_IsPublic,ShortName,LongNamePrivate"
)


def _profile_url(name_or_id: str) -> str:
    return f"https://www.wikitree.com/wiki/{name_or_id}"


def _coerce_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_public(profile: dict[str, Any]) -> bool:
    """WikiTree returns `Privacy_IsPublic` as 1 / 0 / null. Treat anything
    not-truthy as private and skip it."""
    return bool(profile.get("Privacy_IsPublic")) and not profile.get("IsLiving")


def _profile_from_dict(profile: dict[str, Any]) -> GenealogyProfile:
    name = (
        profile.get("LongNamePrivate")
        or profile.get("ShortName")
        or profile.get("Name")
        or "Unknown"
    )
    pid = str(profile.get("Name") or profile.get("Id") or "")
    return GenealogyProfile(
        provider="wikitree",
        provider_id=pid,
        name=str(name),
        summary=_short_summary(profile),
        url=_profile_url(pid) if pid else None,
        birth=_coerce_str(profile.get("BirthDate")),
        death=_coerce_str(profile.get("DeathDate")),
        birth_place=_coerce_str(profile.get("BirthLocation")),
        death_place=_coerce_str(profile.get("DeathLocation")),
        raw=None,
    )


def _short_summary(profile: dict[str, Any]) -> str:
    bits: list[str] = []
    birth = _coerce_str(profile.get("BirthDate"))
    death = _coerce_str(profile.get("DeathDate"))
    place = _coerce_str(profile.get("BirthLocation"))
    if birth:
        bits.append(f"b. {birth}")
    if death:
        bits.append(f"d. {death}")
    if place:
        bits.append(place)
    return " | ".join(bits)


@dataclass(slots=True)
class WikiTreeProvider(GenealogyProvider):
    client: httpx.AsyncClient
    name: str = "wikitree"

    async def search(
        self,
        query: str,
        *,
        k: int,
        birth_year: int | None = None,
        death_year: int | None = None,
        place: str | None = None,
    ) -> list[GenealogyHit]:
        del place  # WikiTree's searchPerson does not accept a place filter.
        first_name, last_name = _split_name(query)
        data = {
            "action": "searchPerson",
            "FirstName": first_name,
            "LastName": last_name,
            "fields": PROFILE_FIELDS,
            "limit": str(k),
            "format": "json",
        }
        if birth_year is not None:
            data["BirthDate"] = f"{birth_year:04d}-01-01"
        if death_year is not None:
            data["DeathDate"] = f"{death_year:04d}-12-31"
        envelope = as_list(await self._post(data))
        if envelope is None or not envelope:
            return []
        first = as_dict(envelope[0])
        if first is None:
            return []
        matches = as_list(first.get("matches"))
        if matches is None:
            return []
        out: list[GenealogyHit] = []
        for index, raw in enumerate(matches):
            profile = as_dict(raw)
            if profile is None:
                continue
            if not _is_public(profile):
                continue
            pid = str(profile.get("Name") or profile.get("Id") or "")
            if not pid:
                continue
            display = (
                profile.get("LongNamePrivate")
                or profile.get("ShortName")
                or profile.get("Name")
                or pid
            )
            out.append(
                GenealogyHit(
                    provider=self.name,
                    provider_id=pid,
                    name=str(display),
                    summary=_short_summary(profile),
                    url=_profile_url(pid),
                    birth=_coerce_str(profile.get("BirthDate")),
                    death=_coerce_str(profile.get("DeathDate")),
                    place=_coerce_str(profile.get("BirthLocation")),
                    score=max(0.0, 1.0 - (index / max(1, len(matches)))),
                )
            )
        return out

    async def get_person(self, provider_id: str) -> GenealogyProfile:
        data = {
            "action": "getPerson",
            "key": provider_id,
            "fields": PROFILE_FIELDS,
            "format": "json",
        }
        envelope = as_list(await self._post(data))
        if envelope is None or not envelope:
            raise ExternalProviderError(f"wikitree returned no profile for {provider_id!r}")
        first = as_dict(envelope[0])
        if first is None:
            raise ExternalProviderError(
                f"wikitree returned non-object envelope for {provider_id!r}"
            )
        profile = as_dict(first.get("person"))
        if profile is None:
            raise ExternalProviderError(f"wikitree returned no `person` field for {provider_id!r}")
        if not _is_public(profile):
            raise ExternalProviderError(
                f"wikitree profile {provider_id!r} is not public; refusing to fetch"
            )
        relatives = await self._get_relatives(provider_id)
        base = _profile_from_dict(profile)
        return GenealogyProfile(
            provider=base.provider,
            provider_id=base.provider_id,
            name=base.name,
            summary=base.summary,
            url=base.url,
            birth=base.birth,
            death=base.death,
            birth_place=base.birth_place,
            death_place=base.death_place,
            relatives=relatives,
            raw=None,
        )

    async def _get_relatives(self, key: str) -> list[GenealogyRelative]:
        data = {
            "action": "getRelatives",
            "keys": key,
            "fields": PROFILE_FIELDS,
            "getParents": "1",
            "getSpouses": "1",
            "getSiblings": "1",
            "getChildren": "1",
            "format": "json",
        }
        envelope = as_list(await self._post(data))
        if envelope is None or not envelope:
            return []
        first = as_dict(envelope[0])
        if first is None:
            return []
        items = as_list(first.get("items"))
        if items is None or not items:
            return []
        first_item = as_dict(items[0])
        if first_item is None:
            return []
        person_dict = as_dict(first_item.get("person"))
        if person_dict is None:
            return []
        out: list[GenealogyRelative] = []
        for relation_key, label in (
            ("Parents", "parent"),
            ("Spouses", "spouse"),
            ("Siblings", "sibling"),
            ("Children", "child"),
        ):
            rels = as_dict(person_dict.get(relation_key))
            if rels is None:
                continue
            for raw_rel in rels.values():
                rel_dict = as_dict(raw_rel)
                if rel_dict is None:
                    continue
                if not _is_public(rel_dict):
                    continue
                rel_id = str(rel_dict.get("Name") or rel_dict.get("Id") or "")
                if not rel_id:
                    continue
                out.append(
                    GenealogyRelative(
                        provider=self.name,
                        provider_id=rel_id,
                        relation=label,
                        name=str(
                            rel_dict.get("LongNamePrivate")
                            or rel_dict.get("ShortName")
                            or rel_dict.get("Name")
                            or rel_id
                        ),
                        url=_profile_url(rel_id),
                        birth=_coerce_str(rel_dict.get("BirthDate")),
                        death=_coerce_str(rel_dict.get("DeathDate")),
                    )
                )
        return out

    async def _post(self, data: dict[str, str]) -> object:
        return await request_json(
            self.client, "POST", WIKITREE_API_URL, label="wikitree", data=data
        )

    async def aclose(self) -> None:
        await self.client.aclose()


def _split_name(query: str) -> tuple[str, str]:
    """WikiTree's `searchPerson` wants FirstName / LastName separately. We
    do a best-effort split: everything up to the last token is FirstName,
    the last token is LastName. Single-token queries are treated as a last
    name, which surfaces broader matches."""
    parts = query.strip().split()
    if not parts:
        return ("", "")
    if len(parts) == 1:
        return ("", parts[0])
    return (" ".join(parts[:-1]), parts[-1])


def build_wikitree_provider(*, user_agent: str, timeout_s: float) -> WikiTreeProvider:
    return WikiTreeProvider(
        client=build_http_client(timeout_s=timeout_s, user_agent=user_agent),
    )
