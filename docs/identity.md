# Identity, authentication and authorization (Phases 2-4)

Status: implemented, **not yet executed**. See "Verification status" at the end.

## Tables

| Table | Purpose | Notable constraints |
|---|---|---|
| `institutions` | Universities. Seeded with Makerere, Kyambogo, MUST, UCU, IUIU. | unique name/slug/code |
| `users` | Accounts. Email stored lower-case. Users are suspended, never deleted. | `email = lower(email)`; status in (ACTIVE, SUSPENDED) |
| `student_profiles` | One per student: institution, optional student number and year. `program_id` is reserved (FK arrives with the academic structure). | one per user; unique (institution, student_number); year 1-8; institution FK is RESTRICT |
| `roles`, `permissions`, `role_permissions` | RBAC catalog. `permissions.platform_only` marks permissions that scoped roles never grant. | unique name / code |
| `user_roles` | A role held by a user. `institution_id` NULL = platform-wide, set = that institution only. | two partial unique indexes (NULL-safe) |
| `refresh_tokens` | Opaque tokens, **hash only**, grouped in families for rotation and reuse detection. | unique hash; revoked_reason check |
| `verification_tokens`, `password_reset_tokens` | One-time tokens, hash only, with expiry and `used_at`. | unique hash |
| `audit_logs` | Append-only security trail. A trigger rejects UPDATE and DELETE. | outcome check; actor FK RESTRICT |

All primary keys are UUIDs (`gen_random_uuid()`); timestamps are `timestamptz`.
Migration: `alembic/versions/20261003_0900_0001_identity_foundation.py` (reference data is a frozen snapshot;
`tests/test_database_constraints.py` fails if `rbac/catalog.py` and the database diverge).

## Authentication flow

1. **Register** `POST /api/v1/auth/register`: creates user + student profile + STUDENT role scoped to the chosen
   institution + an email verification token. Argon2id hash. No tokens are issued; the user signs in next.
2. **Login** `POST /auth/login`: returns `{access_token, token_type, expires_in}` (JWT, 15 min, HS256 pinned,
   iss/aud validated) and sets the refresh token as an **HttpOnly** cookie scoped to `/api/v1/auth`.
   The refresh token is never in a response body.
3. **Refresh** `POST /auth/refresh`: rotates the refresh token (old one marked `rotated`, new one in the same family).
   Presenting an already-rotated token revokes the **entire family** and writes `auth.refresh_reuse_detected`.
4. **Logout** `POST /auth/logout`: revokes the family and clears the cookie (idempotent).
5. **Verify / forgot / reset**: `POST /auth/verify`, `/auth/forgot-password` (identical response for any email),
   `/auth/reset-password` (single use; revokes every session).
6. **Current user** `GET /api/v1/me`: profile, role assignments and the caller's (permission, institution) grants.

The web app keeps the access token **in memory only**. On load it calls `/auth/refresh` (the browser sends the
cookie) to restore the session. Concurrent refreshes are de-duplicated because refresh tokens are single use.

## Authorization model

* Handlers declare permissions, never role names: `Depends(require_permission("user:suspend"))`.
* That route gate only proves the permission is held **somewhere**. The service then applies the scope:
  `authorize_over_user(...)` or `Principal.can(permission, institution_id)`.
* Scope rules: a platform-wide grant satisfies any institution; a scoped grant satisfies only its institution;
  a platform-level operation needs a platform-wide grant.
* `platform_only` permissions (`institution:manage`, `role:manage`, `settings:manage`) are ignored for scoped
  assignments, so a scoped ADMIN cannot gain them.
* Objects outside the caller's scope return **404, not 403**, so ids cannot be probed. A user holding a platform-wide
  role can only be acted on by platform-wide holders.
* Privilege escalation: granting a role needs `role:assign` for the scope being granted, so a scoped admin cannot
  create platform-wide roles or roles in other institutions.
* The user and their grants are re-read on **every** request: suspension and role changes apply immediately,
  not when the access token expires.
* Object ownership helper for later modules: `Principal.ensure_access(owner_id=..., permission=..., institution_id=...)`.

## Endpoints

`/auth/{register,login,refresh,logout,verify,forgot-password,reset-password}`, `GET /me`,
`GET /institutions` (public, active only), `GET /users/{id}` (user:read), `POST /users/{id}/suspend` and `/reinstate`
(user:suspend), `POST /users/{id}/roles`, `DELETE /users/{id}/roles/{role}?institution_id=` (role:assign).
Bootstrap the first admin: `python -m app.cli create-platform-admin --email ... --name ...` (password via hidden prompt).

## Security decisions

* Argon2id; passwords bounded to 10-128 characters; dummy hash verified for unknown emails (timing).
* Generic login failure; suspension is only revealed after a correct password.
* Registration does reveal that an email is taken (the user must be told). Login and reset do not.
* Refresh/logout also reject a foreign `Origin` (CSRF defence in depth on top of SameSite=Lax).
* Rate limits: per account and per IP (IP limit is 5x, because campuses share NAT addresses). `Retry-After` is sent.
  `X-Forwarded-For` is only trusted when `TRUSTED_PROXY_COUNT` is set, using the Nth hop from the right.
* Audit rows never contain passwords or tokens (keys are scrubbed). Failed logins are committed before the error is returned.
* Production: cookies are `Secure`; the email provider is disabled (nothing is sent, nothing is logged) until implemented.

## Known limitations

* **Email delivery is not implemented.** Development logs messages to the console; production sends nothing, so
  verification and reset emails do not arrive until a provider is added. The web app has no verify-email or
  reset-password page yet, so those links are dead in the UI (the API endpoints work).
* Rate limiting is in-process (per API instance); move to Redis before running more than one instance.
* Refresh sessions are sliding with no absolute lifetime cap. Two browser tabs refreshing at the same instant can
  trip reuse detection and sign the user out (no grace window yet).
* No MFA/OTP, resend-verification endpoint, or account lockout beyond rate limiting.
* No guard against revoking the last platform administrator.
* Unverified-email users can sign in; later phases decide which actions require verification.
* The frontend uses a fetch-level mock helper (`src/test/mock-api.ts`) rather than MSW (see README); Playwright E2E is Phase 14.

## Verification status

Written and statically cross-checked (imports, model/migration columns and indexes) but **not executed**: no
database, pytest, npm, ruff, mypy, tsc or eslint run has happened. Run `scripts/verify-phase1.sh`, then paste failures.
