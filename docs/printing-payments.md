# Printing and payments (Phases 8-9)

Status: implemented, **only partly executed**. The pure logic (pricing, both state machines, FakeProvider signing:
52 unit tests) was run and passes. Everything that needs PostgreSQL, FastAPI, npm or a browser has **not** been run.

## Printing

**Tables:** `print_shops` (per institution; several allowed), `print_shop_staff` (which operator works where),
`print_pricing_rules`, `print_documents`, `print_orders`, `print_order_items`, `order_status_history`.

**Documents.** `POST /print/documents` accepts PDF and images only. The **server counts the pages** (pypdf) because the
page count drives the price; a client-supplied count is ignored. Content is identified by magic bytes, size is capped,
storage keys are generated (`print/<student id>/<random>.pdf`), files are PRIVATE, and encrypted/unreadable/huge PDFs are
rejected before anything is stored.

**Pricing** (`printing/pricing.py`, pure, integer UGX). Rules: `PER_PAGE` by (paper size, colour, optional duplex),
`PER_COPY` and `PER_ORDER` extras keyed by `option_key` (staple, binding, ...). New options are new rows, not new columns.
The client never sends a price. It may send `expected_total_ugx` as a stale-price guard; a mismatch is a 409 `price_changed`.
Each order stores a **price snapshot** (rule ids, quantities, unit and line amounts) so the price can be reproduced even if
the shop changes its prices later.

**Order state machine** (`printing/state.py`, tested exhaustively):

    DRAFT -> SUBMITTED -> ACCEPTED -> PRINTING -> READY_FOR_PICKUP -> COMPLETED
    SUBMITTED/ACCEPTED -> REJECTED (operator, reason required);  DRAFT/SUBMITTED/ACCEPTED -> CANCELLED (student)

Status changes go through one function (`move`); anything else is refused. Database CHECKs back it up:
`COMPLETED` requires `PAID`; an `ONLINE` order cannot be past `SUBMITTED` unless `PAID`; an order's shop must belong to its
institution (composite FK).

**Pay-on-pickup.** Student chooses it at checkout -> order is UNPAID. At pickup the operator first **records the cash**
(`POST /operator/orders/{id}/payment`, amount must equal the total; creates a `payments` row with provider `CASH`, an audit
event, and sets the order PAID) and then **confirms pickup** with the student's **pickup code** (`.../complete`). The code is
an HMAC of the order id (not stored); only the owning student sees it, only when the order is ready.
Abuse controls (configurable): outstanding pay-on-pickup orders per student (default 2, per-shop override), a maximum
pay-on-pickup order total, a maximum of open orders, and a per-shop switch to disable pay-on-pickup.

**Who can do what.** Students: only their own orders (404 otherwise). Operators: only orders of shops they are *staff* of,
and only with the role permission for that institution. Administrators with `order:manage_any` act within their institution.
Drafts are invisible to shops. Every operator access to a student's document is audited.

**Retention.** `python -m app.cli purge-print-documents` (schedule daily) deletes document files from storage after
`PRINT_RETENTION_DAYS` (30) once the order is closed, **unless** the order has a retention hold, a payment is still pending,
or a refund is still waiting. Uploads that never became part of an order are purged after 24 h. Order records, prices and
history are kept; only the files go.

## Payments

**Tables:** `payments` (one table for print orders and premium resources), `payment_transactions` (every provider call),
`payment_events` (every verified webhook; **UNIQUE (provider, provider_event_id)**), `refunds`.
Payment status is separate from order status: UNPAID / PENDING / PAID / FAILED / REFUNDED (state machines in `state.py`).

**Provider abstraction** (`providers/payments/base.py`): `initiate`, `verify`, `parse_webhook`, `refund`. Only `FakeProvider`
exists (HMAC-signed, timestamped webhooks; in-memory state). No real provider has been chosen. In **production the fake
provider is treated as unavailable**: online options disappear and the API answers 503; pay-on-pickup keeps working.

**Flow.** `POST /payments {order_id | resource_id}` (the amount is read from the server, never sent) -> a PENDING row is
committed **before** calling the provider -> provider checkout. Then the webhook pipeline:

1. verify the signature and timestamp (invalid -> 401, nothing stored);
2. de-duplicate with `INSERT ... ON CONFLICT DO NOTHING` on the event id (duplicate -> 200, no side effects);
3. **re-verify with the provider** (`verify()`), because the webhook body is never proof; if the provider is unreachable the
   whole transaction rolls back (including the event row) and we return 503 so the provider retries;
4. in ONE transaction: mark PAID, advance the order (`payment_status`) or grant the entitlement, write audit + event rows.

A wrong amount is never marked paid (audited). A frontend "success" page is never proof: `/payments/:id` only shows what the
server says and offers "check again" (`POST /payments/{id}/verify`, same code path).

**Idempotency.** `Idempotency-Key` on `POST /print/orders` and `POST /payments` (a replay returns the original; a different
payload with the same key is a 409); partial unique indexes allow one live payment per order and per buyer+resource;
duplicate webhooks, re-sends under new event ids, and replayed payments change nothing (one `payment.paid` audit row, one
entitlement). Late confirmations (after expiry, or after the student started a new attempt) are honoured; a late payment
for a cancelled order queues a refund; a duplicate charge is flagged for manual refund.

**Refunds.** Cancelling/rejecting a paid online order queues a `refunds` row; staff with `payment:manage` process it
(`POST /payments/{id}/refund`). Refunding a premium purchase revokes the entitlement. Cash refunds are manual.

**Premium purchase.** The same pipeline grants an entitlement (source PURCHASE, reference = payment id) in the webhook transaction.

## Endpoints

Student: `POST /print/documents`, `/print/quote`, `/print/orders` (+`Idempotency-Key`), `GET /print/orders[/{id}]`,
`POST /print/orders/{id}/submit|cancel`, `GET /print/shops`, `/print/shops/{id}/pricing`.
Shop admin (`printshop:manage`): `POST|PATCH /print/shops`, staff, pricing rules.
Operator: `GET /operator/shops|orders[/{id}]`, `POST /operator/orders/{id}/accept|reject|printing|ready|payment|complete|hold`,
`.../items/{item}/document-link`.
Payments: `GET /payments/config`, `POST /payments`, `GET /payments/{id}`, `POST /payments/{id}/verify|refund`,
`POST /payments/webhooks/{provider}`, `POST /payments/dev/simulate` (development only; 404 in production).

## Frontend

`/print` (shop, upload, options, server price, payment choice), `/print/orders[/:id]` (history, tracking, pickup code, Pay now,
cancel), `/operator` and `/operator/orders/:id` (queue, accept/reject/print/ready, cash, pickup, document access),
`/pay/fake/:id` (development checkout), `/payments/:id` (return page), and a real Buy button on premium resources.

## Not done / limitations

* **No real payment provider.** Online payment works only against the FakeProvider and is disabled in production.
* **No notifications.** Status changes are recorded in `order_status_history` and the audit log; delivering them (in-app,
  SMS, push) is the notifications phase. "No duplicate notifications" is therefore only covered indirectly: duplicate
  webhooks create no duplicate order transitions, audit rows or entitlements.
* Only PDF and images are printable (Word/PowerPoint need server-side rendering to count pages reliably).
* Page counting uses pypdf on untrusted files (size-capped); run it in a resource-limited worker before real launch.
* The in-memory FakeProvider and rate limiter are per-process.
* Refunds of COMPLETED orders are not supported (the database forbids a completed order that is not PAID).
* No printer/job-queue integration; "printing" is an operator-confirmed status.
* The E2E suite needs the seeded demo data, a Chromium install and both servers; it is not in CI.

## Verification status

Executed here: 52 pure unit tests (pricing, state machines, FakeProvider), Python/TypeScript import resolution, a
model-vs-migration column/index cross-check (38 tables), identifier-length check. **Not executed:** migrations, pytest
integration tests, ruff, mypy, npm, tsc, eslint, vitest, the build, Playwright. Run `scripts/verify-phase1.sh`.
