# ADR-0002: Use a hosted LLM API for document classification and extraction

- **Status:** Proposed (becomes Accepted when the pull request is merged)
- **Date:** 2026-10-21
- **Deciders:** EcoTrace team
- **Issue:** #20

## Context

Document Intake must classify incoming documents (electricity bills, fuel slips, warehouse issue slips, purchase invoices) and extract fields with a confidence score per field. The [project brief](../project-brief.md) (section 4) planned a small local model through Ollama, with a rule-based fallback so the demo works without a GPU.

Since then:

- The team laptops cannot run a local vision model next to the core (one has 6 GB RAM and no GPU). The core already runs in a 16 GB codespace.
- Real documents are often phone photos of paper slips in Vietnamese. Small local models and plain OCR (Tesseract `vie`) read these poorly and do not understand layouts.
- The organiser demo on 2026-10-22 must show extraction working reliably.

## Decision

1. Document Intake calls a hosted LLM API, chosen with `AI_PROVIDER`:
   - **`gemini` (default):** the Gemini API through Google's `google-genai` SDK (Apache-2.0), model `gemini-3.8-flash` (`GEMINI_MODEL`). The team chose it on 2026-10-21 because its free tier needs no payment.
   - **`claude`:** the Claude API through the official Anthropic SDK (`anthropic`, MIT), model `claude-opus-5-5` (`CLAUDE_MODEL`), effort `low` (`CLAUDE_EFFORT`). This needs prepaid API credits.
   - PDFs and images are sent as they are. There is no separate OCR step.
2. The answer format is **built from the tenant's `document-types.yaml`** and enforced with structured outputs (JSON schema): allowed document types, field names, and a value, unit and confidence per field. A new document type or field is a configuration change, not a code change. Values are normalised (numbers, ISO dates) after the call.
3. **Rule-based fallback** (keywords and regular expressions from the same `document-types.yaml`) is used when no API key is configured or when the API fails (invalid key, rate limit, network error, refusal). The service never stops accepting documents because the AI is unavailable. Fallback results get low confidence and are flagged for review.
4. With Claude, the **server-side refusal fallback** (`fallbacks: "default"`) is enabled, so a rare safety decline is retried on Anthropic's recommended fallback model instead of failing.
5. **API keys only come from the environment** (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`): a GitHub Codespaces secret today, OpenBao later. It is never written to the repository or to `.env.example`.
6. The extractor is one module with one entry point (`extract`). A local model provider (for example Ollama) can be added behind it later without touching the rest of the service.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Local LLM through Ollama (brief section 4) | Needs a GPU or far more RAM than the team has; weaker on Vietnamese phone photos. Remains possible later as an alternative provider for on-premise customers |
| Tesseract `vie` or PaddleOCR plus rules | Reads text but not layout or meaning; every document template needs new rules. Kept in spirit as the rule-based fallback |
| Claude only | Better tested in this project, but needs prepaid credits; kept as the `claude` provider |

## Consequences

- **Gemini's free tier lets Google use the submitted content to improve its products** (Google's pricing page, "Used to improve our products: Yes" for the free tier; "No" for the paid tier). Only the fictional sample documents may be sent on the free tier. Real company documents require the paid tier or another provider.
- **Both APIs are proprietary hosted services, not OSI-licensed components.** It is not shipped with EcoTrace and is optional: without a key, the platform keeps working with the rule-based fallback. Everything that is shipped stays under OSI licenses ([docs/licenses.md](../licenses.md)). The team must be ready to explain this to the jury.
- **Documents leave the company's premises** when AI extraction is on. Before production use, a tenant must be able to opt in or out (planned: an `ai` setting in `tenant.yaml`), and the provider's data-retention terms must be reviewed.
- **Cost:** free on Gemini's free tier (with rate limits); a few US cents per document with `claude-opus-5-5`.
- **Network dependency.** If the API is unreachable, uploads still succeed through the fallback, with lower confidence.
- The brief's mention of Ollama in section 4 is superseded by this ADR for the demo and Phase 3.
