"""Tools that delegate to subagents. Each tool here is a thin wrapper that
pulls the active `SubagentRunner` off `ToolContext` and dispatches to the
appropriate subagent entry-point. The actual subagent loops live in
`my_family_tree.agent.*`."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from my_family_tree.agent.traversal_subagent import TraversalSubagentResult
from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry

registry = get_registry()


class TraverseAndSummarizeInput(BaseModel):
    person_id: UUID
    question: str = Field(min_length=1, max_length=2000)
    max_generations: int = Field(default=4, ge=1, le=10)


@registry.tool(
    name="traverse_and_summarize",
    description=(
        "Delegate a multi-generation tree-walking question to a read-only "
        "subagent. The subagent runs in its own context window with only the "
        "read tools (`person_search`, `person_get`, `person_traverse`, "
        "`person_relations`, `person_count_relations`), walks as deep as the "
        "question requires up to `max_generations`, and returns a concise "
        "summary plus the person summaries it surfaced. Use this only when "
        "the user explicitly asked for a multi-generation walk or an "
        "aggregate over many relatives; for one-hop kin questions prefer "
        "`person_relations`, and for counts prefer `person_count_relations`."
    ),
    input_model=TraverseAndSummarizeInput,
    output_model=TraversalSubagentResult,
    capability=Capability.READ,
)
async def traverse_and_summarize(
    ctx: ToolContext, payload: TraverseAndSummarizeInput
) -> TraversalSubagentResult:
    runner = ctx.subagent_runner
    if runner is None:
        raise RuntimeError(
            "traverse_and_summarize requires a configured subagent runner; "
            "the chat router wires this up automatically. If you are seeing "
            "this from a test, construct a ToolContext with a runner."
        )
    return await runner.run_traversal(
        question=payload.question,
        person_id=payload.person_id,
        max_generations=payload.max_generations,
        parent_ctx=ctx,
    )
