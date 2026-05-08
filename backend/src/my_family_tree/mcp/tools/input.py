"""`request_user_input` tool: lets the agent ask the user a clarifying question
mid-loop and pause the run until the user replies. The chat loop watches for
this tool name and emits a `needs_input` event before halting; the persisted
`tool_result.output` echoes the question/options so the UI can rehydrate the
prompt card after a reload without keeping transient state on the turn."""

from __future__ import annotations

from pydantic import BaseModel, Field

from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry

registry = get_registry()


class RequestUserInputInput(BaseModel):
    reason: str = Field(
        min_length=1,
        max_length=2000,
        description="The question to pose to the user, in plain prose.",
    )
    options: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of suggested answers. The UI renders each as a "
            "clickable button that submits the option text as the user's "
            "next message. Free-text replies are still accepted."
        ),
    )
    schema_hint: str | None = Field(
        default=None,
        description=(
            "Optional JSON Schema (as a string) describing the shape of the "
            "expected reply. The frontend may render an inline form."
        ),
    )


class RequestUserInputOutput(BaseModel):
    """Output echoes the inputs verbatim so the persisted `tool_result` row
    carries the question/options into the next turn for both rehydration and
    the agent's own re-read of its prior assistant turn."""

    acknowledged: bool = True
    question: str
    options: list[str] | None = None
    schema_hint: str | None = None


@registry.tool(
    name="request_user_input",
    description=(
        "Pause the chat to ask the user a clarifying question. The loop "
        "halts after this call (no further tool calls are made on this "
        "turn) and the UI surfaces the question with any provided options "
        "as clickable buttons. The user's next message is treated as the "
        "answer. Use this only when you genuinely cannot proceed without a "
        "decision (conflicting dates, ambiguous person identity, missing "
        "consent for a major write); never as a substitute for proposing."
    ),
    input_model=RequestUserInputInput,
    output_model=RequestUserInputOutput,
    capability=Capability.TRIVIAL_WRITE,
    is_read_only=False,
)
async def request_user_input(
    ctx: ToolContext, payload: RequestUserInputInput
) -> RequestUserInputOutput:
    del ctx
    return RequestUserInputOutput(
        question=payload.reason,
        options=payload.options,
        schema_hint=payload.schema_hint,
    )
