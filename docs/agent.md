# Agent

The chat agent loop lives at `backend/src/my_family_tree/agent/loop.py`. It
streams events from the configured LLM provider, dispatches tool calls via the
in-process `ToolHost`, and re-enters the provider with tool results until the
provider stops or budgets are exhausted.

## Provider abstraction

`backend/src/my_family_tree/llm/base.py` defines a small Protocol with two
methods, `complete()` and `stream()`, plus provider-neutral dataclasses
(`Message`, `ContentBlock`, `ToolSpec`, `ToolUseBlock`, `ToolResultBlock`,
`ThinkingBlock`, `StreamEvent`). Two adapters implement it:

- `llm/openai_provider.py` targets the OpenAI Responses API. `reasoning.effort`
  is plumbed through (`high` by default).
- `llm/anthropic_provider.py` targets the Anthropic Messages API. Extended
  thinking is enabled via a token budget mapped from `reasoning.effort`.
  `cache_control: ephemeral` is applied to the system prompt and tool catalog.

Raw thinking content is never persisted. We keep a summary block on `message`
rows only.

## Subagents

- **Deep research** (`agent/deep_research.py`): triggered explicitly or by the
  chat agent. Larger budgets, web tools enabled, runs as an arq job. Output is
  a set of proposals the user reviews.
- **Conflict resolver** (`agent/conflict_resolver.py`): given a conflict ID,
  produces a single `proposal(action='resolve_conflict')`.

## "I need user input on X"

The agent calls `request_user_input(reason, options?, schema?)`. The runtime
pauses the run with `status=needs_input`, emits a `needs_input` SSE event, and
resumes when the user answers via the API.
