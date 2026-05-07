# External research

The chat agent has read-only tools that reach the public web and a small
set of well-credited genealogy APIs. Findings worth keeping flow into the
same vector knowledge base the rest of the system already searches over.

Every provider is optional. If a key is missing or a provider is disabled,
the corresponding tool is hidden from the agent's catalog (gated by
`enabled_when` predicates on the MCP registry). The rest of the app runs
unchanged with no extra error handling on the call site.

## Providers

| Provider     | Auth                                                                | Pricing                                                |
| ------------ | ------------------------------------------------------------------- | ------------------------------------------------------ |
| Tavily       | `WEB_SEARCH_PROVIDER=tavily` + `TAVILY_API_KEY`                     | Free tier; metered after.                              |
| Brave Search | `WEB_SEARCH_PROVIDER=brave` + `BRAVE_API_KEY`                       | Free tier (2,000 queries/month); metered after.        |
| WikiTree     | none. Opt out with `WIKITREE_ENABLED=false`.                        | Free; no auth for public profiles. Be polite (UA set). |
| Wikidata     | none. Opt out with `WIKIDATA_ENABLED=false`.                        | Free; structured genealogy properties.                 |
| FamilySearch | `FAMILYSEARCH_CLIENT_ID` + `FAMILYSEARCH_CLIENT_SECRET` (OAuth2)    | Free for personal use; developer registration needed.  |

## MCP tools

| Tool                       | Capability         | Provider             |
| -------------------------- | ------------------ | -------------------- |
| `web_search`               | `WEB \| READ`      | Tavily or Brave      |
| `web_fetch`                | `WEB \| READ`      | any URL              |
| `genealogy_search`         | `WEB \| READ`      | aggregated           |
| `wikitree_get_person`      | `WEB \| READ`      | WikiTree             |
| `familysearch_get_person`  | `WEB \| READ`      | FamilySearch         |
| `wikidata_get_entity`      | `WEB \| READ`      | Wikidata             |
| `external_index_url`       | `WEB \| TRIVIAL_WRITE` | any URL          |

## Safety guards

`backend/src/my_family_tree/external/http.py` enforces three things on
every fetch (both `web_fetch` and `external_index_url`):

- **SSRF**. Hosts that resolve to private (`10/8`, `172.16/12`, `192.168/16`),
  loopback, link-local (`169.254/16`, `fe80::/10`), multicast, or otherwise
  reserved IPv4 / IPv6 ranges are rejected. Non-`http`/`https` schemes are
  rejected. Redirects are followed manually so each hop is re-validated.
- **Response size**. Default cap of 5 MB; aborted mid-stream when exceeded
  (configurable via `WEB_SEARCH_MAX_BYTES`).
- **Content type allowlist**. `text/html`, `text/plain`,
  `application/xhtml+xml`, `application/xml`. Binary types are refused
  outright; pdf/image still flow through the upload + OCR pipeline.

FamilySearch profiles flagged `living=true` are refused with a clear error
so the knowledge base never carries living-person data.

## Read -> index -> propose flow

The chat agent's preferred flow when grounding a proposal in external
evidence:

```
genealogy_search("Jane Doe", birth_year=1900) or web_search(...)
   |
   v
external_index_url(<url>)         -> document_id, source_id
   |
   v
hybrid_search(...)                 (optional: confirm against the now-
                                     indexed page or other tree docs)
   |
   v
person_propose_create / event_propose_create / ...
   rationale_md: "Source: web doc <document_id> (<url>): <excerpt>"
```

The user reviews and approves the proposal as usual; the existing applier
materializes the canonical row plus a synthetic `user_assertion` Source
linked to the chat run, so the audit trail back to the chat conversation
is preserved automatically.

## Worked example

With `WEB_SEARCH_PROVIDER=tavily TAVILY_API_KEY=sk-... WIKITREE_ENABLED=true`:

> User: "Find my great-uncle Jane Doe's WikiTree profile and add her parents."
>
> Agent calls `genealogy_search("Jane Doe")`, picks the best match by score,
> then `wikitree_get_person("Doe-1234")`. Reads the parents off the
> response. Calls `external_index_url("https://www.wikitree.com/wiki/Doe-1234")`
> to capture the page in the knowledge base. Proposes one
> `person_propose_create` per parent with the WikiTree URL cited in
> `rationale_md`.

## Configuration reference

See `.env.example` for the full list of variables. The most important ones:

```
# Web search
WEB_SEARCH_PROVIDER=                # "" | "tavily" | "brave"
TAVILY_API_KEY=
BRAVE_API_KEY=
WEB_SEARCH_MAX_RESULTS=8
WEB_SEARCH_REQUEST_TIMEOUT_S=20.0
WEB_SEARCH_MAX_BYTES=5000000

# Genealogy
WIKITREE_ENABLED=true
WIKIDATA_ENABLED=true
FAMILYSEARCH_CLIENT_ID=
FAMILYSEARCH_CLIENT_SECRET=
FAMILYSEARCH_ENVIRONMENT=production # "integration" | "beta" | "production"
GENEALOGY_USER_AGENT=my-family-tree/0.1 (+https://github.com/rlefkowitz/my-family-tree)
GENEALOGY_MAX_RESULTS=10
GENEALOGY_REQUEST_TIMEOUT_S=30.0
```

After flipping any of these, restart the api container so `Settings()` is
re-read; the registry filter pulls from the live `Settings` snapshot.
