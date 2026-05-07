# Agent

The chat agent loop lives at `backend/src/my_family_tree/agent/loop.py`. It
streams events from the configured LLM provider, dispatches tool calls via the
in-process `ToolHost`, and re-enters the provider with tool results until the
provider stops or budgets are exhausted.

## End-to-end record persistence

The agent isn't just a chat box. When you tell it "I am Ryan, born 1932-04-15,
my parents are Jane and John, my brothers are Mary and Peter," it fans
that out into proposals via the propose-write tools, and the response stream
includes both the live tool calls and a summary pill linking to the
`/proposals` page.

```
chat input -> POST /api/v1/chat/stream
        |
        v
ChatAgent.run_turn
   -> provider.stream  (text deltas + tool_use blocks)
   -> ToolHost.call    (validates input, calls registered tool)
        -> mcp/tools/persons.person_propose_create  (writes proposal row)
        -> mcp/tools/relationships.relationship_propose_create
        -> mcp/tools/events.event_propose_create
   -> next provider turn with the tool results
   -> done event with proposal_ids[]
        |
        v
Frontend renders ToolCallCards and a 📋 pill linking to /proposals
        |
        v
User clicks Approve (or Approve all)
        |
        v
POST /api/v1/proposals/{id}/approve
   -> services/proposal_apply.apply_proposal
        -> per (action, target_type) handler
        -> services/provenance.write_user_claims  (Source + Claim + FactProvenance)
   -> proposal.status=approved, applied_at, target_id
```

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

## SSE wire format

`POST /api/v1/chat/stream` returns `text/event-stream`. The frontend reads
it with `frontend/src/api/sse.ts`. Event types:

| Event               | When                                       | Payload                                |
| ------------------- | ------------------------------------------ | -------------------------------------- |
| `start`             | Before the first provider call             | `{conversation_id?}`                   |
| `text_delta`        | Each token from the assistant              | `{text}`                               |
| `thinking_delta`    | Anthropic extended-thinking summary tokens | `{text}`                               |
| `tool_use_started`  | Provider began emitting a tool call        | `{id, name}`                           |
| `tool_use_finished` | Tool call args fully received              | `{id, name, input}`                    |
| `tool_result`       | ToolHost returned a result                 | `{tool_use_id, output, is_error}`      |
| `usage`             | End-of-stream token usage                  | `{input_tokens, output_tokens, ...}`   |
| `done`              | Final event of the turn                    | `{stop_reason, proposal_ids[], usage}` |
| `error`             | Provider or tool exception                 | `{message}`                            |

## Subagents

- **Deep research** (`agent/deep_research.py`): triggered explicitly or by the
  chat agent. Larger budgets, web tools enabled, runs as an arq job. Output is
  a set of proposals the user reviews. v2 work.
- **Conflict resolver** (`agent/conflict_resolver.py`): given a conflict ID,
  produces a single `proposal(action='resolve_conflict')`. v2 work.

## "I need user input on X"

The agent calls `request_user_input(reason, options?, schema?)`. v1.5 returns
an acknowledgement and the agent continues by including the question in its
text output; the user replies in the next chat turn. A genuine async resume
that fetches the queued question is v2.
