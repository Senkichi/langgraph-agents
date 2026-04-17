# Task: Design a testing strategy for a real-time pricing service

A Python service consumes supplier price updates from Kafka, applies a rules
engine, and publishes the resulting prices to a downstream topic. It must
serve 10k updates per second with <100ms end-to-end latency. The rules engine
has historically been the source of most incidents — subtle arithmetic bugs
that pass unit tests but surface on production traffic.

Design a testing strategy for this service. Cover unit, integration, load,
and production-verification layers. Name concrete tooling. Explain which
tests gate which deployment step.

## Expected response shape (for eval reference only, not shown to pipeline)
- Length: long
- Key concepts:
  - unit tests
  - property-based testing
  - integration tests
  - load test
  - canary
  - shadow traffic
  - golden dataset
  - regression
  - kafka
  - latency SLO
  - alerting
- Failure modes:
  - recommends only unit tests
  - no concrete tooling named
  - ignores the "subtle arithmetic bug" failure mode that motivated the task
  - conflates load testing with performance profiling
