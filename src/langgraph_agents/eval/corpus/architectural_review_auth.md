# Task: Review and harden this authentication design

A team is proposing the following authentication scheme for a new B2B
product:

- JWTs signed with HS256 using a shared secret stored in each service's
  environment variables.
- Tokens are valid for 30 days, are never refreshed, and include the user's
  full permission set embedded as claims.
- On logout, the client deletes the token locally; the server has no
  revocation mechanism.
- Password reset emails link to a URL containing a single-use token valid
  for 7 days.
- Rate limiting is applied only to the login endpoint, at 100 requests per
  IP per minute.

Produce a review of this design and a concrete hardening plan. Name each
specific risk, the scenario that exploits it, and the fix you recommend.
Separate "must fix before launch" from "should fix within 90 days."

## Expected response shape (for eval reference only, not shown to pipeline)
- Length: long
- Key concepts:
  - HS256
  - RS256
  - asymmetric
  - revocation
  - short-lived
  - refresh token
  - rotation
  - rate limiting
  - account enumeration
  - password reset
  - token leakage
  - JWT
  - blacklist
  - session
  - IP-based limit
  - distributed rate limit
- Failure modes:
  - no critique of the 30-day lifetime with no revocation
  - no critique of shared HS256 secret rotation
  - misses that rate limit only on login leaves password reset flood open
  - rubber-stamps as "mostly fine"
  - missing distinction between launch-blocker and nice-to-have
