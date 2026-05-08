"""External integrations: web search, genealogy lookups, and URL fetching.

Every provider in this package is optional. `from_settings(...)` constructors
return `None` when no key or flag is configured, which the MCP tool gating
layer reads via `enabled_when` predicates so the agent never sees a tool it
cannot actually call."""
