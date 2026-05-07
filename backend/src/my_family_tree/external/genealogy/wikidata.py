"""Wikidata genealogy provider. https://www.wikidata.org/

Wikidata is a no-auth, structured, public-domain knowledge graph with deep
coverage of historical figures and family relationships. We use:

- `wbsearchentities` to find QIDs by free-text query.
- `Special:EntityData/<QID>.json` to pull the full entity claims.

The properties we surface are the standard genealogy ones:

- P22 father
- P25 mother
- P26 spouse
- P40 child
- P569 date of birth
- P570 date of death
- P19 place of birth
- P20 place of death
"""

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

WIKIDATA_SEARCH_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY_URL = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"

RELATION_PROPERTIES: dict[str, str] = {
    "P22": "father",
    "P25": "mother",
    "P26": "spouse",
    "P40": "child",
}

DATE_PROPERTIES: dict[str, str] = {
    "P569": "birth",
    "P570": "death",
}

PLACE_PROPERTIES: dict[str, str] = {
    "P19": "birth_place",
    "P20": "death_place",
}


def _entity_url(qid: str) -> str:
    return f"https://www.wikidata.org/wiki/{qid}"


def _claim_value_id(claim: dict[str, Any]) -> str | None:
    mainsnak = claim.get("mainsnak")
    if not isinstance(mainsnak, dict):
        return None
    datavalue = mainsnak.get("datavalue")
    if not isinstance(datavalue, dict):
        return None
    value = datavalue.get("value")
    if isinstance(value, dict):
        qid = value.get("id")
        if isinstance(qid, str):
            return qid
    return None


def _claim_time_value(claim: dict[str, Any]) -> str | None:
    mainsnak = claim.get("mainsnak")
    if not isinstance(mainsnak, dict):
        return None
    datavalue = mainsnak.get("datavalue")
    if not isinstance(datavalue, dict):
        return None
    value = datavalue.get("value")
    if not isinstance(value, dict):
        return None
    time = value.get("time")
    if not isinstance(time, str):
        return None
    return time.lstrip("+")


@dataclass(slots=True)
class WikidataProvider(GenealogyProvider):
    client: httpx.AsyncClient
    name: str = "wikidata"
    language: str = "en"

    async def search(
        self,
        query: str,
        *,
        k: int,
        birth_year: int | None = None,
        death_year: int | None = None,
        place: str | None = None,
    ) -> list[GenealogyHit]:
        del birth_year, death_year, place  # wbsearchentities does not filter by these.
        params = {
            "action": "wbsearchentities",
            "search": query,
            "language": self.language,
            "format": "json",
            "limit": str(k),
            "type": "item",
        }
        payload = as_dict(await self._get(WIKIDATA_SEARCH_URL, params=params))
        if payload is None:
            return []
        results = as_list(payload.get("search"))
        if results is None:
            return []
        out: list[GenealogyHit] = []
        for index, raw in enumerate(results):
            item = as_dict(raw)
            if item is None:
                continue
            qid = item.get("id")
            label = item.get("label") or item.get("title") or ""
            description = item.get("description") or ""
            if not isinstance(qid, str) or not qid:
                continue
            out.append(
                GenealogyHit(
                    provider=self.name,
                    provider_id=qid,
                    name=str(label),
                    summary=str(description),
                    url=_entity_url(qid),
                    birth=None,
                    death=None,
                    place=None,
                    score=max(0.0, 1.0 - (index / max(1, len(results)))),
                )
            )
        return out

    async def get_person(  # noqa: PLR0912  branchy: wikidata claims are deeply nested
        self, provider_id: str
    ) -> GenealogyProfile:
        url = WIKIDATA_ENTITY_URL.format(qid=provider_id)
        payload = as_dict(await self._get(url))
        if payload is None:
            raise ExternalProviderError(f"wikidata returned non-object for {provider_id!r}")
        entities = as_dict(payload.get("entities"))
        if entities is None:
            raise ExternalProviderError(f"wikidata response missing `entities` for {provider_id!r}")
        entity_dict = as_dict(entities.get(provider_id))
        if entity_dict is None:
            raise ExternalProviderError(f"wikidata returned no entity for {provider_id!r}")
        labels = as_dict(entity_dict.get("labels"))
        descriptions = as_dict(entity_dict.get("descriptions"))
        label = ""
        description = ""
        if labels is not None:
            entry = as_dict(labels.get(self.language) or labels.get("en"))
            if entry is not None and isinstance(entry.get("value"), str):
                label = entry["value"]
        if descriptions is not None:
            entry = as_dict(descriptions.get(self.language) or descriptions.get("en"))
            if entry is not None and isinstance(entry.get("value"), str):
                description = entry["value"]
        claims_raw = as_dict(entity_dict.get("claims"))
        claims: dict[str, list[dict[str, Any]]] = {}
        if claims_raw is not None:
            for key, value in claims_raw.items():
                if not isinstance(key, str):
                    continue
                value_list = as_list(value)
                if value_list is None:
                    continue
                claims[key] = [
                    item for item in (as_dict(v) for v in value_list) if item is not None
                ]
        birth = _first_date(claims.get("P569", []))
        death = _first_date(claims.get("P570", []))
        birth_place = await self._first_place_label(claims.get("P19", []))
        death_place = await self._first_place_label(claims.get("P20", []))
        relatives: list[GenealogyRelative] = []
        for prop, label_ in RELATION_PROPERTIES.items():
            for claim in claims.get(prop, []):
                qid = _claim_value_id(claim)
                if qid is None:
                    continue
                relative_label = await self._label_for(qid)
                relatives.append(
                    GenealogyRelative(
                        provider=self.name,
                        provider_id=qid,
                        relation=label_,
                        name=relative_label or qid,
                        url=_entity_url(qid),
                    )
                )
        return GenealogyProfile(
            provider=self.name,
            provider_id=provider_id,
            name=label or provider_id,
            summary=description,
            url=_entity_url(provider_id),
            birth=birth,
            death=death,
            birth_place=birth_place,
            death_place=death_place,
            relatives=relatives,
            raw=None,
        )

    async def _first_place_label(self, claims: list[dict[str, Any]]) -> str | None:
        for claim in claims:
            qid = _claim_value_id(claim)
            if qid is None:
                continue
            label = await self._label_for(qid)
            if label is not None:
                return label
        return None

    async def _label_for(self, qid: str) -> str | None:
        params = {
            "action": "wbgetentities",
            "ids": qid,
            "props": "labels",
            "languages": f"{self.language}|en",
            "format": "json",
        }
        payload = as_dict(await self._get(WIKIDATA_SEARCH_URL, params=params))
        if payload is None:
            return None
        entities = as_dict(payload.get("entities"))
        if entities is None:
            return None
        entity = as_dict(entities.get(qid))
        if entity is None:
            return None
        labels = as_dict(entity.get("labels"))
        if labels is None:
            return None
        for code in (self.language, "en"):
            entry = as_dict(labels.get(code))
            if entry is not None and isinstance(entry.get("value"), str):
                return entry["value"]
        return None

    async def _get(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
    ) -> object:
        return await request_json(
            self.client, "GET", url, label="wikidata", params=params
        )

    async def aclose(self) -> None:
        await self.client.aclose()


def _first_date(claims: list[dict[str, Any]]) -> str | None:
    for claim in claims:
        time = _claim_time_value(claim)
        if time:
            return time
    return None


def build_wikidata_provider(*, user_agent: str, timeout_s: float) -> WikidataProvider:
    return WikidataProvider(
        client=build_http_client(timeout_s=timeout_s, user_agent=user_agent),
    )
