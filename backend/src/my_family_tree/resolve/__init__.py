"""Resolve module: person dedup, conflict detection rules, and merge."""

from my_family_tree.resolve.conflicts import (
    ConflictCandidate,
    detect_conflicts_for_person,
    stable_conflict_id,
)
from my_family_tree.resolve.dedup import (
    DedupCandidate,
    DedupScore,
    block_candidates,
    score_candidates,
)
from my_family_tree.resolve.merge import merge_persons

__all__ = [
    "ConflictCandidate",
    "DedupCandidate",
    "DedupScore",
    "block_candidates",
    "detect_conflicts_for_person",
    "merge_persons",
    "score_candidates",
    "stable_conflict_id",
]
