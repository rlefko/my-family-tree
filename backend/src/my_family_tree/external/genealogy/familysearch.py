"""FamilySearch genealogy provider. https://www.familysearch.org/developers/

OAuth2 client_credentials flow: trade `client_id` + `client_secret` for a
short-lived bearer token, cache it in-process minus a 60-second leeway, and
attach `Authorization: Bearer ...` to every API call.

We deliberately refuse to fetch profiles that FamilySearch flags as
`living=true`: their TOS restricts redistribution of living-person data,
and our knowledge base would otherwise leak that into chunks the agent can
re-cite later. Returning an `ExternalProviderError` makes the refusal
visible to the agent so it knows not to retry."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal, cast

import httpx
from pydantic import SecretStr

from my_family_tree.core.errors import ExternalProviderError
from my_family_tree.external.genealogy.base import (
    GenealogyHit,
    GenealogyProfile,
    GenealogyProvider,
    GenealogyRelative,
    as_dict,
    as_list,
    split_query_name,
)
from my_family_tree.external.http import build_http_client, request_json

_TOKEN_URL = "https://ident.familysearch.org/cis-web/oauth2/v3/token"  # noqa: S105
_TOKEN_LEEWAY_S = 60
_HTTP_NOT_FOUND = 404

_PRODUCTION_BASE = "https://api.familysearch.org"
_BETA_BASE = "https://beta.familysearch.org"
_INTEGRATION_BASE = "https://integration.familysearch.org"


def _api_base(environment: Literal["integration", "beta", "production"]) -> str:
    if environment == "integration":
        return _INTEGRATION_BASE
    if environment == "beta":
        return _BETA_BASE
    return _PRODUCTION_BASE


@dataclass(slots=True)
class _CachedToken:
    value: str
    expires_at: float

    def fresh(self, now: float) -> bool:
        return now + _TOKEN_LEEWAY_S < self.expires_at


@dataclass(slots=True)
class FamilySearchProvider(GenealogyProvider):
    client_id: SecretStr
    client_secret: SecretStr
    environment: Literal["integration", "beta", "production"]
    client: httpx.AsyncClient
    name: str = "familysearch"
    _token: _CachedToken | None = field(default=None, init=False)

    async def search(  # noqa: PLR0912  branchy because the gedcomx response is heavily nested
        self,
        query: str,
        *,
        k: int,
        birth_year: int | None = None,
        death_year: int | None = None,
        place: str | None = None,
    ) -> list[GenealogyHit]:
        params: dict[str, str] = {"q.givenName": "", "q.surname": ""}
        first, last = split_query_name(query)
        params["q.givenName"] = first
        params["q.surname"] = last
        if birth_year is not None:
            params["q.birthLikeDate"] = str(birth_year)
        if death_year is not None:
            params["q.deathLikeDate"] = str(death_year)
        if place:
            params["q.anyPlace"] = place
        params["count"] = str(k)
        url = f"{_api_base(self.environment)}/platform/tree/search"
        payload_obj = await self._get(url, params=params)
        payload = as_dict(payload_obj)
        if payload is None:
            return []
        entries_raw = as_list(payload.get("entries"))
        if entries_raw is None:
            return []
        out: list[GenealogyHit] = []
        for index, raw in enumerate(entries_raw):
            entry = as_dict(raw)
            if entry is None:
                continue
            content = as_dict(entry.get("content"))
            if content is None:
                continue
            person_raw = as_dict(content.get("gedcomx") or {})
            if person_raw is None:
                continue
            persons = as_list(person_raw.get("persons"))
            if persons is None or not persons:
                continue
            person_dict = as_dict(persons[0])
            if person_dict is None:
                continue
            if person_dict.get("living") is True:
                continue
            pid = str(person_dict.get("id") or "")
            if not pid:
                continue
            display = _display_name(person_dict) or pid
            facts = _facts_summary(person_dict)
            out.append(
                GenealogyHit(
                    provider=self.name,
                    provider_id=pid,
                    name=display,
                    summary=facts.summary,
                    url=f"https://www.familysearch.org/tree/person/details/{pid}",
                    birth=facts.birth,
                    death=facts.death,
                    place=facts.birth_place,
                    score=max(0.0, 1.0 - (index / max(1, len(entries_raw)))),
                )
            )
        return out

    async def get_person(self, provider_id: str) -> GenealogyProfile:
        url = f"{_api_base(self.environment)}/platform/tree/persons/{provider_id}"
        payload = as_dict(await self._get(url))
        if payload is None:
            raise ExternalProviderError(f"familysearch returned non-object for {provider_id!r}")
        persons = as_list(payload.get("persons"))
        if persons is None or not persons:
            raise ExternalProviderError(f"familysearch returned no person for {provider_id!r}")
        person_dict = as_dict(persons[0])
        if person_dict is None:
            raise ExternalProviderError(
                f"familysearch returned non-object person for {provider_id!r}"
            )
        if person_dict.get("living") is True:
            raise ExternalProviderError(
                f"familysearch profile {provider_id!r} is flagged living; refusing to fetch"
            )
        facts = _facts_summary(person_dict)
        relatives = await self._fetch_relatives(provider_id)
        return GenealogyProfile(
            provider=self.name,
            provider_id=provider_id,
            name=_display_name(person_dict) or provider_id,
            summary=facts.summary,
            url=f"https://www.familysearch.org/tree/person/details/{provider_id}",
            birth=facts.birth,
            death=facts.death,
            birth_place=facts.birth_place,
            death_place=facts.death_place,
            relatives=relatives,
            raw=None,
        )

    async def _fetch_relatives(self, provider_id: str) -> list[GenealogyRelative]:
        url = f"{_api_base(self.environment)}/platform/tree/persons/{provider_id}/families"
        payload = as_dict(await self._get(url, allow_404=True))
        out: list[GenealogyRelative] = []
        if payload is None:
            return out
        relationships = as_list(payload.get("relationships"))
        if relationships is None:
            return out
        for raw in relationships:
            rel = as_dict(raw)
            if rel is None:
                continue
            kind = rel.get("type") or ""
            relation = _relationship_label(str(kind), rel, provider_id)
            if relation is None:
                continue
            other_id, name = _other_party(rel, provider_id)
            if other_id is None:
                continue
            out.append(
                GenealogyRelative(
                    provider=self.name,
                    provider_id=other_id,
                    relation=relation,
                    name=name or other_id,
                    url=f"https://www.familysearch.org/tree/person/details/{other_id}",
                )
            )
        return out

    async def _get(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        allow_404: bool = False,
    ) -> object:
        token = await self._access_token()
        return await request_json(
            self.client,
            "GET",
            url,
            label="familysearch",
            allow_status=(_HTTP_NOT_FOUND,) if allow_404 else (),
            params=params,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/x-gedcomx-v1+json",
            },
        )

    async def _access_token(self) -> str:
        now = time.monotonic()
        token = self._token
        if token is not None and token.fresh(now):
            return token.value
        payload = await request_json(
            self.client,
            "POST",
            _TOKEN_URL,
            label="familysearch token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id.get_secret_value(),
                "client_secret": self.client_secret.get_secret_value(),
            },
            headers={"Accept": "application/json"},
        )
        token_payload = as_dict(payload)
        if token_payload is None:
            raise ExternalProviderError("familysearch token response was not an object")
        access = token_payload.get("access_token")
        if not isinstance(access, str) or not access:
            raise ExternalProviderError("familysearch token response missing access_token")
        expires_in = token_payload.get("expires_in")
        ttl = float(expires_in) if isinstance(expires_in, int | float) else 3600.0
        self._token = _CachedToken(value=access, expires_at=now + ttl)
        return access

    async def aclose(self) -> None:
        await self.client.aclose()


@dataclass(slots=True, frozen=True)
class _Facts:
    summary: str
    birth: str | None
    death: str | None
    birth_place: str | None
    death_place: str | None


def _facts_summary(person: dict[str, Any]) -> _Facts:
    facts = person.get("facts")
    birth = death = birth_place = death_place = None
    if isinstance(facts, list):
        for raw in facts:
            if not isinstance(raw, dict):
                continue
            fact = cast(dict[str, Any], raw)
            kind = fact.get("type")
            date_node = fact.get("date")
            place_node = fact.get("place")
            date_text = (
                date_node.get("original")
                if isinstance(date_node, dict) and isinstance(date_node.get("original"), str)
                else None
            )
            place_text = (
                place_node.get("original")
                if isinstance(place_node, dict) and isinstance(place_node.get("original"), str)
                else None
            )
            if kind == "http://gedcomx.org/Birth":
                birth = date_text
                birth_place = place_text
            elif kind == "http://gedcomx.org/Death":
                death = date_text
                death_place = place_text
    summary_bits = []
    if birth:
        summary_bits.append(f"b. {birth}")
    if death:
        summary_bits.append(f"d. {death}")
    if birth_place:
        summary_bits.append(birth_place)
    return _Facts(
        summary=" | ".join(summary_bits),
        birth=birth,
        death=death,
        birth_place=birth_place,
        death_place=death_place,
    )


def _display_name(person: dict[str, Any]) -> str | None:
    names = person.get("names")
    if not isinstance(names, list):
        return None
    for raw in names:
        if not isinstance(raw, dict):
            continue
        forms = raw.get("nameForms")
        if not isinstance(forms, list):
            continue
        for form in forms:
            if not isinstance(form, dict):
                continue
            full = form.get("fullText")
            if isinstance(full, str) and full.strip():
                return full
    return None


def _relationship_label(kind: str, rel: dict[str, Any], anchor_id: str) -> str | None:
    """Map FamilySearch relationship types onto the labels we use across
    providers: parent, spouse, child."""
    if "ParentChild" in kind:
        # In FamilySearch, person1 is the parent and person2 the child.
        person1 = rel.get("person1")
        person2 = rel.get("person2")
        if isinstance(person1, dict) and person1.get("resourceId") == anchor_id:
            return "child"
        if isinstance(person2, dict) and person2.get("resourceId") == anchor_id:
            return "parent"
        return None
    if "Couple" in kind:
        return "spouse"
    return None


def _other_party(rel: dict[str, Any], anchor_id: str) -> tuple[str | None, str | None]:
    person1 = rel.get("person1")
    person2 = rel.get("person2")
    other = None
    if isinstance(person1, dict) and person1.get("resourceId") != anchor_id:
        other = person1
    elif isinstance(person2, dict) and person2.get("resourceId") != anchor_id:
        other = person2
    if not isinstance(other, dict):
        return (None, None)
    other_dict = cast(dict[str, Any], other)
    other_id = other_dict.get("resourceId")
    if not isinstance(other_id, str):
        return (None, None)
    return (other_id, None)


def build_familysearch_provider(
    *,
    client_id: SecretStr,
    client_secret: SecretStr,
    environment: Literal["integration", "beta", "production"],
    timeout_s: float,
    user_agent: str,
) -> FamilySearchProvider:
    return FamilySearchProvider(
        client_id=client_id,
        client_secret=client_secret,
        environment=environment,
        client=build_http_client(timeout_s=timeout_s, user_agent=user_agent),
    )
