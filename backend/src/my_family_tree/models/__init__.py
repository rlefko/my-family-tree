"""SQLModel tables.

Importing this module registers every table on
`my_family_tree.db.base.metadata`, which Alembic uses for autogenerate.
The `db.base` import below MUST come first so the custom MetaData (with naming
convention) is bound to `SQLModel.metadata` before any model class is built.
"""

from my_family_tree.db import base as _db_base
from my_family_tree.models import enums
from my_family_tree.models.agent_run import AgentRun
from my_family_tree.models.chunk import Chunk
from my_family_tree.models.claim import Claim, FactProvenance
from my_family_tree.models.conflict import Conflict, ConflictClaim
from my_family_tree.models.conversation import Conversation
from my_family_tree.models.document import Document, DocumentText
from my_family_tree.models.event import Event, EventParticipant
from my_family_tree.models.inference_cache import InferenceCache
from my_family_tree.models.message import Message
from my_family_tree.models.person import Alias, Person
from my_family_tree.models.place import Place
from my_family_tree.models.proposal import Proposal
from my_family_tree.models.relationship import Relationship
from my_family_tree.models.source import Source
from my_family_tree.models.tree import Tree

__all__ = [
    "AgentRun",
    "Alias",
    "Chunk",
    "Claim",
    "Conflict",
    "ConflictClaim",
    "Conversation",
    "Document",
    "DocumentText",
    "Event",
    "EventParticipant",
    "FactProvenance",
    "InferenceCache",
    "Message",
    "Person",
    "Place",
    "Proposal",
    "Relationship",
    "Source",
    "Tree",
    "enums",
]
