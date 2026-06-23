# Session 05 Implementation: Conversational Memory

## Overview

This implementation adds conversational session support to the estimator service, transforming it from a stateless transactional API into a multi-turn conversational system.

## Architecture Decisions

### 1. File Attachment Processing: Local Extraction (Camino B)

**Choice:** Local text extraction with `pypdf` and `python-docx`

**Rationale:**
- Provider-agnostic: works with any LLM, not just multimodal APIs
- Prepares foundation for RAG chunking in Module 3
- Full control over text preprocessing and cleaning
- No additional API costs per file

**Trade-offs:**
- Requires more code than direct multimodal upload
- May miss visual content from PDFs (diagrams, tables)
- Memory overhead for large files (mitigated with 10MB limit)

### 2. Project Metadata Extraction: LLM-Based

**Choice:** Dedicated LLM call with structured JSON output

**Rationale:**
- Robust to varied user phrasing
- Structured output with Pydantic validation
- Educational value (demonstrates secondary LLM call pattern)

**Trade-offs:**
- Adds one LLM call per conversation turn (~0.5s latency)
- Additional token cost (~500 tokens per turn)
- Alternative (regex/heuristics) would be faster but less robust

### 3. Memory Strategy: Sliding Window (6 turns)

**Choice:** Preserve last 6 user+assistant pairs plus system prompt

**Rationale:**
- Bounded memory consumption
- Simple implementation (no summarization logic needed)
- 6 turns = ~12 messages typically fits in context window
- System prompt regenerated on each turn with updated metadata

**Limitations:**
- Older context is lost (no long-term memory)
- No semantic importance ranking
- Future: Add summarization for key facts before discarding

### 4. Session Storage: In-Memory Dictionary

**Choice:** Process-scoped dictionary, no persistence

**Rationale:**
- Acceptable for educational phase and single-instance deployments
- Zero infrastructure dependencies (no Redis/DB setup)
- Explicitly documented as volatile in code comments

**Migration path:**
- Session 08+ will add Redis for multi-instance deployments
- Clear separation of `SessionStore` makes this refactor straightforward

## Data Flow

```
Client Request
  ↓
[POST /sessions/{id}/estimate]
  ↓
1. Process attachments → extract text
  ↓
2. Retrieve session (history + metadata)
  ↓
3. Render prompt with metadata injection
  ↓
4. Add user message to history
  ↓
5. Call LLM with full conversation history
  ↓
6. Add assistant response to history
  ↓
7. Extract metadata from turn → update session
  ↓
8. Update system prompt with new metadata
  ↓
Response (estimation + metadata + turn number)
```

## Testing Strategy

- **Unit tests:** Session models, sliding window logic, file extraction
- **Integration tests:** Multi-turn context preservation, sliding window enforcement
- **Manual testing:** Streamlit UI for end-to-end user experience

## Future Enhancements (Out of Scope)

- Summarization strategy for long conversations
- Persistent storage (Redis/database)
- Memory compression with semantic anchors
- Dynamic tier selection based on user profile
- Search integration for external context
