# Task: Produce a refactoring roadmap for a legacy monolith module

Produce a step-by-step refactoring roadmap for `checkout_processor.py`, a notorious 12,000 LOC Python file in our e-commerce monolith. 

The module suffers from specific smells:
- A God Class `OrderManager` with 85 methods.
- Deeply nested conditionals handling 14 different legacy payment gateways.
- Pervasive ambient state relying on a module-level dictionary `CURRENT_CTX` mutated unpredictably.
- Vague null returns instead of proper exception handling or Option types.

Constraints:
- You must not regress any existing behavior, no matter how obscure.
- The team cannot pause feature work; your refactoring must ship continuously in increments behind feature flags.

Rank the roadmap steps by risk-adjusted leverage. For each step, explicitly name the testing and observability scaffolding required before modifying the code.

## Expected response shape (for eval reference only, not shown to pipeline)
- Length: long
- Key concepts:
  - dependency injection
  - strangler fig
  - facade pattern
  - characterization tests
  - feature flag
  - pure function
  - cyclomatic complexity
  - ambient state
  - global variable
  - test coverage
  - shadow mode
- Failure modes:
  - proposes a big-bang rewrite or pausing feature work to clean up the code
  - fails to address the concurrency risks of the module-level dictionary (ambient state)
  - ignores the requirement to detail the testing/observability scaffolding needed *before* changing code
  - suggests feature flagging at the file level rather than functional/routing level for the monolith
