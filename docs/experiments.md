# Experiments

Short records of things we tried, including what we dropped and why.

## Search grounding for place attributes (2026-10-28) — dropped

**Question.** Can Muse Spark's `web_search` tool verify the attributes people ask for (wifi, vegan
options, outdoor seating, accessibility) for the final top 3 destinations, at most $0.02 per plan,
marking an attribute "verified" only when the answer carries a source URL from the search?

**Availability.** Yes: `web_search` is a tool on the Responses API (not Chat Completions);
answers carry `url_citation` annotations and, with `include: ["web_search_call.results"]`, the raw
results. Pricing: $2.50 per 1,000 searches plus tokens (dev.meta.ai/docs/search-grounding,
dev.meta.ai/docs/pricing-rate-limits).

**Probes** (one request per plan, all 3 places in one call, `search_context_size: low`):

| Probe | Searches | Tokens in / out | Cost | Result |
| --- | --- | --- | --- | --- |
| 3 places × 4 attributes, JSON schema, reasoning low | 11 | 61,238 / 2,006 | $0.083 | output not parseable as JSON; 0 citations |
| 3 places × 1 attribute (wifi), plain text, reasoning minimal, 600 output tokens | 5 | 12,964 / 600 | $0.031 | `incomplete`: ran out of tokens before answering; no URLs |

**Decision.** Dropped. Both probes cost more than the $0.02 per plan limit (the model decides how
many searches to run, so cost is not bounded by the request) and neither returned a single
attribute with a source URL. Attributes stay "unknown" when OpenStreetMap has no tag. Total spent:
$0.114, recorded by the spend guard.
