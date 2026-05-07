"""Chat agent loop. Streams provider events, dispatches tool calls via the
in-process `ToolHost`, and re-enters the provider with tool results until the
provider stops or budgets are exhausted."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

from my_family_tree.agent.budgets import Budgets
from my_family_tree.agent.system_prompt import CHAT_SYSTEM_PROMPT
from my_family_tree.core.logging import get_logger
from my_family_tree.llm.base import (
    LLMProvider,
    Message,
    ReasoningConfig,
    StreamEvent,
    TextBlock,
    ToolResultBlock,
    ToolSpec,
    ToolUseBlock,
)
from my_family_tree.mcp.host import ToolHost

log = get_logger(__name__)


@dataclass(slots=True)
class ChatTurnEvent:
    """Provider-neutral event surfaced to the API SSE layer."""

    type: Literal[
        "text_delta",
        "thinking_delta",
        "tool_use_started",
        "tool_use_finished",
        "tool_result",
        "usage",
        "done",
        "needs_input",
        "error",
    ]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChatAgent:
    provider: LLMProvider
    model: str
    host: ToolHost
    budgets: Budgets = field(default_factory=Budgets)
    system_prompt: str = CHAT_SYSTEM_PROMPT
    reasoning: ReasoningConfig = field(default_factory=lambda: ReasoningConfig(effort="high"))

    async def run_turn(  # noqa: PLR0912  the loop is naturally branchy
        self,
        messages: list[Message],
    ) -> AsyncIterator[ChatTurnEvent]:
        """Run a single chat turn. Yields events as they happen. The caller
        is responsible for persisting the resulting messages.

        On `request_user_input`, the loop pauses and yields a `needs_input`
        event; the caller resumes by appending the user's reply and calling
        `run_turn` again.
        """
        tool_specs = [
            ToolSpec(
                name=spec["name"],
                description=spec["description"],
                input_schema=spec["input_schema"],
            )
            for spec in self.host.specs()
        ]
        tokens_used = 0
        tool_calls_used = 0
        history = list(messages)
        proposal_ids: list[str] = []

        while True:
            assistant_blocks: list[TextBlock | ToolUseBlock] = []
            tool_results: list[ToolResultBlock] = []
            finished = False

            current_tool: dict[str, Any] | None = None
            current_text: list[str] = []

            stream = self.provider.stream(
                model=self.model,
                system=self.system_prompt,
                messages=history,
                tools=tool_specs,
                max_tokens=4096,
                reasoning=self.reasoning,
            )
            async for event in stream:
                async for out in self._handle_event(event, current_tool, current_text):
                    yield out
                if event.type == "tool_use_started":
                    current_tool = {
                        "id": event.tool_use_id,
                        "name": event.tool_name,
                        "input": "",
                    }
                elif event.type == "tool_use_input_delta" and current_tool is not None:
                    current_tool["input"] += event.tool_input_delta or ""
                elif event.type == "tool_use_finished" and current_tool is not None:
                    block, result = await self._execute_tool(current_tool)
                    assistant_blocks.append(block)
                    if current_text:
                        assistant_blocks.insert(
                            0, TextBlock(type="text", text="".join(current_text))
                        )
                        current_text.clear()
                    tool_results.append(result)
                    tool_calls_used += 1
                    if (
                        not result.is_error
                        and isinstance(result.output, dict)
                        and result.output.get("proposal_id") is not None
                    ):
                        proposal_ids.append(str(result.output["proposal_id"]))
                    yield ChatTurnEvent(
                        type="tool_result",
                        payload={
                            "tool_use_id": result.tool_use_id,
                            "output": result.output,
                            "is_error": result.is_error,
                        },
                    )
                    current_tool = None
                elif event.type == "text_delta" and event.text:
                    current_text.append(event.text)
                elif event.type == "usage" and event.usage:
                    tokens_used += event.usage.input_tokens + event.usage.output_tokens
                elif event.type == "done":
                    finished = True
                elif event.type == "error":
                    yield ChatTurnEvent(
                        type="error", payload={"message": event.error_message or ""}
                    )
                    return

            if current_text:
                assistant_blocks.append(TextBlock(type="text", text="".join(current_text)))

            history.append(Message(role="assistant", content=list(assistant_blocks)))
            if tool_results:
                history.append(Message(role="tool", content=list(tool_results)))

            try:
                self.budgets.check(tokens_used=tokens_used, tool_calls_used=tool_calls_used)
            except Exception as e:
                yield ChatTurnEvent(type="error", payload={"message": str(e)})
                return

            if not tool_results or finished:
                yield ChatTurnEvent(
                    type="done",
                    payload={
                        "tokens_used": tokens_used,
                        "tool_calls_used": tool_calls_used,
                        "proposal_ids": list(proposal_ids),
                    },
                )
                return

    async def _handle_event(
        self,
        event: StreamEvent,
        current_tool: dict[str, Any] | None,
        current_text: list[str],
    ) -> AsyncIterator[ChatTurnEvent]:
        del current_tool, current_text
        if event.type == "text_delta":
            yield ChatTurnEvent(type="text_delta", payload={"text": event.text or ""})
        elif event.type == "thinking_delta":
            yield ChatTurnEvent(type="thinking_delta", payload={"text": event.text or ""})
        elif event.type == "tool_use_started":
            yield ChatTurnEvent(
                type="tool_use_started",
                payload={"id": event.tool_use_id, "name": event.tool_name},
            )
        elif event.type == "tool_use_finished":
            yield ChatTurnEvent(
                type="tool_use_finished",
                payload={"id": event.tool_use_id},
            )
        elif event.type == "usage" and event.usage:
            yield ChatTurnEvent(
                type="usage",
                payload={
                    "input_tokens": event.usage.input_tokens,
                    "output_tokens": event.usage.output_tokens,
                    "cached_input_tokens": event.usage.cached_input_tokens,
                    "reasoning_tokens": event.usage.reasoning_tokens,
                },
            )

    async def _execute_tool(
        self, current_tool: dict[str, Any]
    ) -> tuple[ToolUseBlock, ToolResultBlock]:
        try:
            parsed = json.loads(current_tool["input"]) if current_tool["input"] else {}
        except json.JSONDecodeError:
            parsed = {"_raw": current_tool["input"]}
        block = ToolUseBlock(
            type="tool_use",
            id=current_tool["id"],
            name=current_tool["name"],
            input=parsed,
        )
        try:
            result = await self.host.call(current_tool["name"], parsed)
            return block, ToolResultBlock(
                type="tool_result",
                tool_use_id=current_tool["id"],
                output=result.model_dump(mode="json"),
            )
        except Exception as e:
            log.warning("agent.tool_error", tool=current_tool["name"], error=str(e))
            return block, ToolResultBlock(
                type="tool_result",
                tool_use_id=current_tool["id"],
                output={"error": str(e)},
                is_error=True,
            )
