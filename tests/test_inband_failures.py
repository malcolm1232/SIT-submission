"""In-band tool failures (``tools/inband.py``) and readable excerpts (``tools/sources.py``).

A delivered call whose payload reports a failure is built as a tool error by the gateway, and a
source's excerpt is readable text (a hit's title plus snippet, a passage of a fetched page),
never the raw JSON payload.
"""

from __future__ import annotations

import json
from typing import Any

from sit_review_agent.models import ToolCallStatus
from sit_review_agent.tools.gateway import _result
from sit_review_agent.tools.inband import inband_failure, payload_of
from sit_review_agent.tools.sources import extract_sources

FAILED_SEARCH = {"results": [], "provider_used": None,
                 "attempts": [{"provider": "duckduckgo", "outcome": "error", "reason": "No results found.",
                               "failure_code": "unknown_error", "result_count": 0},
                              {"provider": "tavily", "outcome": "skipped", "reason": "TAVILY_API_KEY not configured",
                               "failure_code": "no_api_key", "result_count": 0}]}
SEARCH_OK = {"results": [{"link": "https://www.postgresql.org/docs/current/pgvector.html",
                          "title": "pgvector indexes", "snippet": "HNSW and IVFFlat index types.",
                          "extracted_text": "Long page text."}],
             "provider_used": "duckduckgo", "attempts": [{"provider": "duckduckgo", "outcome": "used"}]}
PAGE_TEXT = ("Azure Service Bus quotas. " + "The standard tier allows at most 2,000 messages per day. " * 15
             + "Premium has no such cap.")
PAGES = [{"title": "Service Bus quotas", "final_url": "https://learn.microsoft.com/azure/service-bus/quotas",
          "extracted_text": PAGE_TEXT, "status": 200}]
FAILED_PAGE = {"title": None, "final_url": "https://example.com/x", "extracted_text": "", "status": "error",
               "error": "net::ERR_NAME_NOT_RESOLVED"}


def _res(server: str, tool: str, text: str, args: dict[str, Any] | None = None, structured: Any = None) -> Any:
    return _result("call-0001", server, tool, args or {"query": "q"}, status=ToolCallStatus.OK,
                   started_at="2026-10-06T09:00:00Z", text=text, structured_content=structured)


# =============================================================================== inband_failure


def test_failed_search_payload_gives_a_reason_naming_the_providers() -> None:
    reason = inband_failure("search_web", FAILED_SEARCH)
    assert reason is not None and "empty result list" in reason and "TAVILY_API_KEY not configured" in reason
    assert inband_failure("search_web", json.dumps(FAILED_SEARCH)) == reason      # the JSON text reads the same


def test_normal_search_payload_is_not_a_failure() -> None:
    assert inband_failure("search_web", SEARCH_OK) is None


def test_page_list_fails_only_when_every_record_fails() -> None:
    assert inband_failure("fetch_page", [FAILED_PAGE, FAILED_PAGE]) is not None
    assert inband_failure("fetch_page", [FAILED_PAGE, PAGES[0]]) is None
    assert inband_failure("fetch_page", payload_of(json.dumps(PAGES), {"result": PAGES})) is None


def test_http_500_in_the_payload_is_a_failure() -> None:
    reason = inband_failure("fetch_page", {"status_code": 500, "extracted_text": "Internal Server Error",
                                           "error": "upstream failed"})
    assert reason is not None and reason.startswith("HTTP 500")


# =============================================================================== extract_sources


def test_search_hit_excerpt_is_title_plus_snippet() -> None:
    srcs = extract_sources(_res("mcp-internet-search", "search_web", json.dumps(SEARCH_OK)))
    assert [s.url_or_citation for s in srcs] == ["https://www.postgresql.org/docs/current/pgvector.html"]
    assert srcs[0].excerpt == "pgvector indexes - HNSW and IVFFlat index types."
    assert "{" not in srcs[0].excerpt and srcs[0].title == "pgvector indexes"


def test_fetched_page_excerpt_is_a_passage_of_its_text() -> None:
    url = "https://learn.microsoft.com/azure/service-bus/quotas"
    srcs = extract_sources(_res("mcp-internet-search", "fetch_page", json.dumps(PAGES), args={"url": url},
                                structured={"result": PAGES}))
    assert len(srcs) == 1 and srcs[0].url_or_citation == url and srcs[0].title == "Service Bus quotas"
    ex = srcs[0].excerpt
    assert "{" not in ex and ex.startswith("Azure Service Bus quotas.") and ex.endswith("per day.")
    assert len(ex) <= 600 and srcs[0].read_in_full and srcs[0].content == PAGE_TEXT


def test_failed_search_gives_no_source() -> None:
    assert extract_sources(_res("mcp-internet-search", "search_web", json.dumps(FAILED_SEARCH))) == []
    assert extract_sources(_res("mcp-internet-search", "search_web", "", structured=FAILED_SEARCH)) == []
