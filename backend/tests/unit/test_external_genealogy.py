"""Tests for the WikiTree, Wikidata, and FamilySearch genealogy providers
plus the `GenealogyService.from_settings` aggregator."""

from __future__ import annotations

import pytest
import respx
from httpx import Response
from pydantic import SecretStr

from my_family_tree.core.config import GenealogyView
from my_family_tree.core.errors import ExternalProviderError
from my_family_tree.external.genealogy.familysearch import (
    _PRODUCTION_BASE,
    _TOKEN_URL,
    build_familysearch_provider,
)
from my_family_tree.external.genealogy.service import GenealogyService
from my_family_tree.external.genealogy.wikidata import (
    WIKIDATA_ENTITY_URL,
    WIKIDATA_SEARCH_URL,
    build_wikidata_provider,
)
from my_family_tree.external.genealogy.wikitree import (
    WIKITREE_API_URL,
    build_wikitree_provider,
)


def _view(**overrides: object) -> GenealogyView:
    defaults: dict[str, object] = {
        "familysearch_client_id": None,
        "familysearch_client_secret": None,
        "familysearch_environment": "production",
        "wikitree_enabled": False,
        "wikitree_user_agent": "ua/test",
        "wikidata_enabled": False,
        "max_results": 5,
        "request_timeout_s": 5.0,
    }
    defaults.update(overrides)
    return GenealogyView(**defaults)  # type: ignore[arg-type]


# -----------------------------------------------------------------------
# Service gating
# -----------------------------------------------------------------------


@pytest.mark.unit
def test_service_returns_none_when_all_disabled() -> None:
    assert GenealogyService.from_settings(_view()) is None


@pytest.mark.unit
def test_service_enables_wikitree_only() -> None:
    service = GenealogyService.from_settings(_view(wikitree_enabled=True))
    assert service is not None
    assert service.has("wikitree")
    assert not service.has("wikidata")
    assert not service.has("familysearch")


@pytest.mark.unit
def test_service_enables_familysearch_when_creds_present() -> None:
    service = GenealogyService.from_settings(
        _view(
            familysearch_client_id=SecretStr("cid"),
            familysearch_client_secret=SecretStr("csec"),
        )
    )
    assert service is not None
    assert service.has("familysearch")


# -----------------------------------------------------------------------
# WikiTree provider
# -----------------------------------------------------------------------


@pytest.mark.unit
@respx.mock
async def test_wikitree_search_filters_private_profiles() -> None:
    respx.post(WIKITREE_API_URL).mock(
        return_value=Response(
            200,
            json=[
                {
                    "matches": [
                        {
                            "Name": "Doe-1",
                            "BirthDate": "1900-01-01",
                            "BirthLocation": "Boston",
                            "Privacy_IsPublic": 1,
                            "IsLiving": 0,
                            "ShortName": "John Doe",
                        },
                        {
                            "Name": "Doe-2",
                            "Privacy_IsPublic": 0,  # private; should be skipped
                            "IsLiving": 0,
                            "ShortName": "Hidden",
                        },
                        {
                            "Name": "Doe-3",
                            "Privacy_IsPublic": 1,
                            "IsLiving": 1,  # living; should be skipped
                            "ShortName": "Alive",
                        },
                    ]
                }
            ],
        )
    )
    provider = build_wikitree_provider(user_agent="ua/test", timeout_s=2.0)
    try:
        results = await provider.search("john doe", k=10)
    finally:
        await provider.aclose()
    assert [r.provider_id for r in results] == ["Doe-1"]


@pytest.mark.unit
@respx.mock
async def test_wikitree_get_person_refuses_private_profile() -> None:
    respx.post(WIKITREE_API_URL).mock(
        return_value=Response(
            200,
            json=[{"person": {"Name": "Doe-9", "Privacy_IsPublic": 0, "IsLiving": 0}}],
        )
    )
    provider = build_wikitree_provider(user_agent="ua/test", timeout_s=2.0)
    try:
        with pytest.raises(ExternalProviderError, match="not public"):
            await provider.get_person("Doe-9")
    finally:
        await provider.aclose()


# -----------------------------------------------------------------------
# Wikidata provider
# -----------------------------------------------------------------------


@pytest.mark.unit
@respx.mock
async def test_wikidata_search_returns_qids() -> None:
    respx.get(WIKIDATA_SEARCH_URL).mock(
        return_value=Response(
            200,
            json={
                "search": [
                    {"id": "Q7259", "label": "Ada Lovelace", "description": "mathematician"},
                    {"id": "Q9249", "label": "Lord Byron", "description": "poet"},
                ]
            },
        )
    )
    provider = build_wikidata_provider(user_agent="ua/test", timeout_s=2.0)
    try:
        results = await provider.search("Ada Lovelace", k=2)
    finally:
        await provider.aclose()
    assert [r.provider_id for r in results] == ["Q7259", "Q9249"]
    assert results[0].name == "Ada Lovelace"


@pytest.mark.unit
@respx.mock
async def test_wikidata_get_entity_extracts_dates_and_relatives() -> None:
    qid = "Q7259"
    entity_url = WIKIDATA_ENTITY_URL.format(qid=qid)
    respx.get(entity_url).mock(
        return_value=Response(
            200,
            json={
                "entities": {
                    qid: {
                        "labels": {"en": {"value": "Ada Lovelace"}},
                        "descriptions": {"en": {"value": "Mathematician"}},
                        "claims": {
                            "P22": [
                                {
                                    "mainsnak": {
                                        "datavalue": {
                                            "value": {"id": "Q9249"},
                                        }
                                    }
                                }
                            ],
                            "P569": [
                                {
                                    "mainsnak": {
                                        "datavalue": {"value": {"time": "+1815-12-10T00:00:00Z"}}
                                    }
                                }
                            ],
                        },
                    }
                }
            },
        )
    )
    # Parent label lookup via the same wbgetentities endpoint
    respx.get(WIKIDATA_SEARCH_URL).mock(
        return_value=Response(
            200,
            json={"entities": {"Q9249": {"labels": {"en": {"value": "Lord Byron"}}}}},
        )
    )
    provider = build_wikidata_provider(user_agent="ua/test", timeout_s=2.0)
    try:
        profile = await provider.get_person(qid)
    finally:
        await provider.aclose()
    assert profile.name == "Ada Lovelace"
    assert profile.birth is not None
    assert "1815" in profile.birth
    assert any(rel.name == "Lord Byron" for rel in profile.relatives)


# -----------------------------------------------------------------------
# FamilySearch provider
# -----------------------------------------------------------------------


@pytest.mark.unit
@respx.mock
async def test_familysearch_caches_oauth_token() -> None:
    token_route = respx.post(_TOKEN_URL).mock(
        return_value=Response(200, json={"access_token": "tok-123", "expires_in": 3600})
    )
    person_route = respx.get(f"{_PRODUCTION_BASE}/platform/tree/persons/KW1F-XYZ").mock(
        return_value=Response(
            200,
            json={
                "persons": [
                    {
                        "id": "KW1F-XYZ",
                        "living": False,
                        "names": [{"nameForms": [{"fullText": "Jane Doe"}]}],
                        "facts": [],
                    }
                ]
            },
        )
    )
    families_route = respx.get(f"{_PRODUCTION_BASE}/platform/tree/persons/KW1F-XYZ/families").mock(
        return_value=Response(200, json={"relationships": []})
    )

    provider = build_familysearch_provider(
        client_id=SecretStr("cid"),
        client_secret=SecretStr("csec"),
        environment="production",
        timeout_s=2.0,
        user_agent="ua/test",
    )
    try:
        first = await provider.get_person("KW1F-XYZ")
        second = await provider.get_person("KW1F-XYZ")
    finally:
        await provider.aclose()

    assert first.name == "Jane Doe"
    assert second.name == "Jane Doe"
    # The token endpoint should be hit exactly once even across two calls.
    assert token_route.call_count == 1
    assert person_route.call_count == 2
    assert families_route.call_count == 2


@pytest.mark.unit
@respx.mock
async def test_familysearch_refuses_living_person() -> None:
    respx.post(_TOKEN_URL).mock(
        return_value=Response(200, json={"access_token": "tok", "expires_in": 3600})
    )
    respx.get(f"{_PRODUCTION_BASE}/platform/tree/persons/LIVE-1").mock(
        return_value=Response(
            200,
            json={
                "persons": [
                    {
                        "id": "LIVE-1",
                        "living": True,
                        "names": [{"nameForms": [{"fullText": "Living Person"}]}],
                        "facts": [],
                    }
                ]
            },
        )
    )
    provider = build_familysearch_provider(
        client_id=SecretStr("cid"),
        client_secret=SecretStr("csec"),
        environment="production",
        timeout_s=2.0,
        user_agent="ua/test",
    )
    try:
        with pytest.raises(ExternalProviderError, match="living"):
            await provider.get_person("LIVE-1")
    finally:
        await provider.aclose()
