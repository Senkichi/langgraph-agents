# Task: Explain prompt caching in 3 sentences

Write a 3-sentence explanation of why prompt caching matters for agentic
workflows. Assume the reader is a mid-level backend engineer who has used
LLM APIs but has never heard of prompt caching.

## Expected response shape (for eval reference only, not shown to pipeline)
- Length: short
- Key concepts: cache, tokens, cost, latency, reuse, prefix, agent, turns
- Failure modes:
  - more than 3 sentences
  - vague without mentioning either cost or latency savings
  - describes LLM caching generically (embeddings, response cache) rather than prompt-prefix caching
