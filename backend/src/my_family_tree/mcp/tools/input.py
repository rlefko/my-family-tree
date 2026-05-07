"""`request_user_input` tool: lets the agent ask the user a clarifying question
mid-loop. v1.5 implementation is minimal: the tool returns a sentinel
acknowledgement and the agent surfaces the question via its text output. The
full async resume (queue the question, pause the run, wake on user reply) is
v2 work; persisting the prompt for that future is the only thing this tool
does for now."""

from __future__ import annotations

from pydantic import BaseModel, Field

from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry

registry = get_registry()


class RequestUserInputInput(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    options: list[str] | None = None
    schema_hint: str | None = Field(
        default=None,
        description=(
            "Optional JSON Schema (as a string) describing the shape of the "
            "expected reply. The frontend may render an inline form."
        ),
    )


class RequestUserInputOutput(BaseModel):
    acknowledged: bool = True
    note: str = Field(
        default=(
            "Pose the question to the user in your reply text. v1 does not "
            "pause the agent run across HTTP turns; the user replies in the "
            "next chat message and you continue from there."
        )
    )


@registry.tool(
    name="request_user_input",
    description=(
        "Acknowledge that you need user input before continuing. The frontend "
        "shows the agent's text reply containing your question; the user "
        "responds in the next chat turn."
    ),
    input_model=RequestUserInputInput,
    output_model=RequestUserInputOutput,
    capability=Capability.TRIVIAL_WRITE,
    is_read_only=False,
)
async def request_user_input(
    ctx: ToolContext, payload: RequestUserInputInput
) -> RequestUserInputOutput:
    del ctx, payload
    return RequestUserInputOutput()
