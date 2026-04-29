# Task: Review and revise this proposed REST API contract

A team is designing a public-facing API for a high-volume ticketing system. Produce a comprehensive review of the following partial specification. Name specific breaking-change risks, data consistency holes, and structural inconsistencies. Provide a concrete, revised JSON contract for the endpoints.

```http
BASE URL: https://api.tickets.com/api?v=1

POST /events/{id}/tickets
Request: { "userId": "12345", "quantity": 2 }
Response (200 OK): { "reservationId": "abc", "status": "held" }
Error (400): { "error": "Not enough tickets available" }

PATCH /reservations/{reservationId}
Request: { "status": "confirmed" }
Response (200 OK): { "reservationId": "abc", "status": "confirmed" }
Error (500): [ "Database timeout" ]

GET /events/{id}/attendees?page=5&limit=100
Response (200 OK): {
  "total": 45000,
  "attendees": [ {"id": "user1", "name": "Alice"}, ... ]
}
```

The system expects tens of thousands of concurrent users trying to reserve tickets for the same event simultaneously. 

## Expected response shape (for eval reference only, not shown to pipeline)
- Length: long
- Key concepts:
  - idempotency key
  - cursor pagination
  - offset drift
  - race condition
  - optimistic concurrency
  - semantic versioning
  - error schema
  - reservation timeout
  - partial update
- Failure modes:
  - fails to identify offset pagination as a performance and accuracy risk for high-volume data
  - misses the lack of idempotency keys on the POST reservation endpoint
  - ignores the inconsistent error response shapes between endpoints
  - accepts query parameter versioning as a best practice without critique
  - does not address the race condition inherent in reserving tickets concurrently
