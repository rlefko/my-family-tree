# Agent

The chat agent loop lives at `backend/src/my_family_tree/agent/loop.py`. It
streams events from the configured LLM provider, dispatches tool calls via the
in-process `ToolHost`, and re-enters the provider with tool results until the
provider stops or budgets are exhausted.

## End-to-end record persistence

The agent isn't just a chat box. When you tell it "Add Jane Doe, born
April 15, 1932 in Boston, with two children John and Mary," it fans that
out into proposals via the propose-write tools, and the response stream
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
| `start`             | Before the first provider call             | `{conversation_id, agent_run_id}`      |
| `text_delta`        | Each token from the assistant              | `{text}`                               |
| `thinking_delta`    | Anthropic extended-thinking summary tokens | `{text}`                               |
| `tool_use_started`  | Provider began emitting a tool call        | `{id, name}`                           |
| `tool_use_finished` | Tool call args fully received              | `{id, name, input}`                    |
| `tool_result`       | ToolHost returned a result                 | `{tool_use_id, output, is_error}`      |
| `usage`             | End-of-stream token usage                  | `{input_tokens, output_tokens, ...}`   |
| `done`              | Final event of the turn                    | `{stop_reason, proposal_ids[], usage}` |
| `error`             | Provider or tool exception                 | `{message}`                            |

The chat router auto-creates a `Conversation` row on the first turn (when the
client sends no `conversation_id`) and an `AgentRun` row for every turn.
Proposals emitted by the agent are stamped with `agent_run_id`, and at
approve time the proposal-applier reads `agent_run.conversation_id` to dedup
the synthetic chat `Source` per conversation. The frontend captures the
`conversation_id` from the `start` event and echoes it on subsequent turns
so the same thread keeps reusing the same Source row.

## Subagents

- **Deep research** (`agent/deep_research.py`): triggered explicitly or by the
  chat agent. Larger budgets, web tools enabled, runs as an arq job. Output is
  a set of proposals the user reviews. v2 work.
- **Conflict resolver** (`agent/conflict_resolver.py`): given a conflict ID,
  produces a single `proposal(action='resolve_conflict')`. v2 work.

## External research

The chat agent reaches beyond uploaded documents through a small set of
optional read tools (Tavily / Brave web search; WikiTree, Wikidata, and
FamilySearch genealogy lookups) plus `external_index_url` for adding the
fetched text to the searchable knowledge base. Every provider is opt-in
via env vars; absent providers are simply hidden from the agent's tool
catalog so the agent never wastes a call on something that cannot work.

A typical external-research turn:

```
genealogy_search / web_search
   |
   v
external_index_url(<url>)        creates a Document(kind=web) + Source
   |                              and runs the ingest pipeline so the
   v                              page is vector-searchable thereafter
person_propose_create / event_propose_create / ...
   rationale_md cites: "Source: web doc <document_id> (<url>): <excerpt>"
```

All fetches go through SSRF, response-size, and content-type guards in
`external/http.py`. See [external-research.md](external-research.md) for
the full provider matrix, configuration, and worked examples.

## "I need user input on X"

The agent calls `request_user_input(reason, options?, schema?)`. v1.5 returns
an acknowledgement and the agent continues by including the question in its
text output; the user replies in the next chat turn. A genuine async resume
that fetches the queued question is v2.
