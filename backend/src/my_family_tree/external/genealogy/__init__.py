"""Genealogy providers behind a shared `GenealogyService` aggregator.

Three sources are wired up: WikiTree (no auth, public profiles), Wikidata
(no auth, structured family graph for historical figures), and FamilySearch
(OAuth client_credentials, opt-in). The service aggregates search across
whichever providers are enabled and exposes per-provider get-by-id calls
for richer detail."""

from my_family_tree.external.genealogy.base import (
    GenealogyHit,
    GenealogyProfile,
    GenealogyProvider,
    GenealogyRelative,
)
from my_family_tree.external.genealogy.service import GenealogyService

__all__ = [
    "GenealogyHit",
    "GenealogyProfile",
    "GenealogyProvider",
    "GenealogyRelative",
    "GenealogyService",
]
