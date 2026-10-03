# SIT MCP server probe: findings (2026-10-03)

The owner ran `scripts/probe_mcp_servers.py` on his Mac at 11:24 on 2026-10-03 (results stamped 11:25:28 +0800, total runtime 71.0 s).
The results are committed as `research/robustness/mcp_probe_results.redacted.json`.
Client: Python 3.13.13, `mcp` 2.2.0, `httpx` 0.28.1, offering protocol 2025-11-25.

## The results file and its redaction

The script writes `mcp_probe_results.json`, and `.gitignore` line 7 ignores that name on purpose.
The rule came in with commit `b730cab` (2026-10-02) from the fresh-eyes audit item N4 (`research/audit/fresh_eyes.md`), which asked for a `.gitignore` before the probe ran because the script writes its raw output inside the repo.
The rule stays; the reviewed copy is committed under the `.redacted.json` name instead.
The probe already replaces the key and its URL-encoded forms (`quote` and `quote_plus`) with `***REDACTED***`, and refuses to write if the raw key survives.
The committed copy also replaces the four server-issued `mcp-session-id` response headers (32 hex characters each) with a placeholder, because a live session id is not needed for any finding.
Secret proof on the raw file, counts only: 64-character `[A-Za-z0-9_-]` tokens 0, tokens of 40 or more such characters 0, `Bearer` followed by a value 0, `api_key=` with a value 0, `sk-` 0, e-mail addresses 0, home-directory paths or the user name 0, `Bearer%20` 0.
The 13 bare `Bearer` hits are the variant label `Authorization: Bearer` and the servers' `WWW-Authenticate: Bearer` challenge; the 2 `x-api-key` hits are variant labels; the one `REDACTED` is `_meta.api_key`.
The same counts on the committed copy are all 0, including 32-hex tokens.

## Authentication

All four servers accepted the first variant tried, the `Authorization` header with the value `Bearer <key>` (HTTP 200, `initialize` ok).
The no-auth control got HTTP 401 with `WWW-Authenticate: Bearer` on every server.
So the shared key is enforced at every server, and `X-API-Key` (the agent's configured guess) was never needed.
The document-intelligence server's own instructions say it "does not currently ... enforce real user/agent authentication", yet it answered 401 without the key, so the key is checked in front of it.

## Per server

### mcp-internet-search (version 4.0.3)

Cold start 34.4 s, warm `initialize` 0.038 s.
Three tools: `search_web`, `fetch_url`, `get_provider_status`.
`search_web` requires `query` (string) and takes `mode` (default `auto`), `provider`, `max_results` (default 5), `fetch_top_n`, `min_results` and `max_chars`.
`fetch_url` requires `urls`, an array, not a single `url` string, and takes `max_chars`.
`get_provider_status` takes an optional boolean `probe` (default false).
The sample call `search_web` with "model context protocol" and `max_results` 3 returned three real results in 4.5 s, the first a Wikipedia page.
The result is JSON with `results` (each with `link`, `title`, `snippet`, `extracted_text`, `content_status`), `provider_used` and `attempts`.

### mcp-browser-automation-pw (server name mcp-browser-automation-playwright, version 4.0.3)

Cold start 29.3 s, warm 0.037 s.
Seven tools: `open_browser` (optional `headless`), `visit_website` (`url`), `login` (`username`, `password` and three CSS selectors, all required), `click_button` (`selector`), `fill_form` (`fields` object, optional `submit_selector`), `extract_data` (optional `selector`) and `close_browser`.
Its instructions state there is exactly one browser session for the whole server, not one per caller, and that it has no domain allowlist.
The probe made no sample call on it.

### mcp-research-information (version 4.0.5)

Cold start 39.5 s, warm 0.042 s.
Seven tools: `search_research` (requires `query`; filters for discipline, dates, publication types, open access, sources; `max_results` default 10), `get_research_work` (any one of `doi`, `pmid`, `pmcid`, `arxiv_id`, `openalex_id`, `semantic_scholar_id`, `title`), `find_related_research`, `resolve_research_access`, `retrieve_research_content` and `get_research_evidence` (each requires `canonical_id`), and `search_research_author` (requires `query`).
Its instructions require resolve before retrieve, and say `retrieve_research_content` only accepts a work whose access was already resolved.
The probe made no sample call on it.

### mcp-document-intelligence (version 4.0.4)

Cold start 70.1 s, warm 0.037 s.
One tool: `read_document`, which requires `uri` and takes `extraction_mode` (default `auto`), `page_range`, `output_format` (default `markdown`), `include_tables`, `include_images`, `language_hint` and `maximum_output_size`.
The sample call passed a plain-text sentence as `uri` and came back in 0.053 s with `is_error: false` but `processing_status: "rejected"`, `content: null` and the warning "scheme not allowed: ''; only file:// and https:// are accepted".
The console summary's reading that it "accepted a plain-text sample" is therefore wrong: the call was answered, not accepted.
The lab brief's statement that the server "currently rejects all inputs" (no allowed local root or remote domains) is neither confirmed nor refuted, because the probe never sent an `https://` document.

## Latency

Every server was cold: the first HTTP response of any status came only with the first successful `initialize`.
Cold starts were 29.3 s to 70.1 s, inside the agent's 150 s `connect_timeout_s` and below the 90 s assumed by robustness INF-01.
Warm `initialize` was 0.037 s to 0.042 s, and a full SDK handshake once warm 0.037 s to 0.046 s.
Server versions were 4.0.3 to 4.0.5, all on protocol 2025-11-25, and the probe recorded zero errors.

## What the probe contradicts or settles

1. `config/tools.yaml` line 3 had `auth_header: X-API-Key`, marked unverified (audit U1); the working shape is `Authorization: Bearer <key>`, now configured, and U1 is closed.
2. Robustness INF-01 and the scenarios preamble assume 1 to 2 minutes, about 90 s, per cold start; the measured worst case is 70.1 s, so the 150 s allowance holds with margin and the "~90 s" progress text is pessimistic, not wrong.
3. The fresh-eyes audit N15 kept the browser off until the probe showed per-client isolation; the server itself states there is one global session and no domain allowlist, so the browser stays off.
4. The console summary's claim that document intelligence now accepts input is not supported by the JSON (point above), so the server stays disabled and ADR-006 item 4 stands until an `https://` document is read through it.
5. The agent hardcodes no tool names: it offers whatever `tools/list` returns, by capability, and the model fills arguments from each tool's schema.
6. The URL policy (`agent/sit_review_agent/tools/policy.py`) recognises a fetch by argument key or by any argument that is a URL, so `fetch_url`'s `urls` array is policed element by element; a unit test now pins this.
7. The search result shape matches the ledger extraction in `agent/sit_review_agent/tools/sources.py` (`results` list, `link` URL key), and `query` is in `QUERY_ARG_KEYS`, so query counting works for `search_web`, `search_research` and `search_research_author`.

## Demo-day consequence

A cold server costs 30 s to 70 s on its first call, a warm one 0.04 s.
All four servers should be warm before the slot.
`dra preflight --warm` warms only the servers enabled in `config/tools.yaml` (internet search and research), so a server switched on live in a §4 modification starts cold.
`docs/DEMO_DAY_RUNBOOK.md` §1 now says so: enable such a server before the T−10 warm-up, or accept up to 70 s on its first call.
The keep-warm loop of §3 (`--keep-warm 120`) stays, because the containers' idle timeout is still unmeasured.

## For a follow-up worker

- A preflight option that warms disabled servers too, so all four are warm whatever §4 enables.
- One `read_document` call with a public `https://` PDF, to settle whether document intelligence works at all (needs the owner, since it reaches the SIT hosts).
- Sample calls on `fetch_url` and the research tools, to record their result shapes; until then `sources.py` treats a multi-URL `fetch_url` call as one source, keyed on the first URL in its text.
- `search_web` with `fetch_top_n` and `retrieve_research_content` fetch pages server-side, so those fetches never pass the agent's URL policy; decide whether to pin `fetch_top_n` to 0 or accept it.
- The idle timeout after which a container scales back to zero, measured on the laptop.
- A `read_document` result with `processing_status: "rejected"` and `is_error: false` would count as a successful call in the gateway; if the server is ever enabled, treat `rejected` and `failed` as tool errors.
