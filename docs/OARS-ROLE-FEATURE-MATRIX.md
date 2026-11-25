# OARS Student Solutions — Role Feature Matrix

**Date:** 25 November 2026
**Agent:** Kiro Code Agent — Master Prompt 10A
**Method:** Direct code inspection, test execution, API trace

---

## Legend

| Status | Meaning |
|---|---|
| **COMPLETE AND VERIFIED** | Implemented, connected to real API, TypeScript clean, covered by passing tests |
| **IMPLEMENTED BUT NOT VERIFIED** | Code written and builds, but not covered by automated tests (requires live database) |
| **PARTIALLY IMPLEMENTED** | Core flow works; some secondary features missing or incomplete |
| **MISSING** | Not yet implemented |
| **BLOCKED** | Cannot be completed without an external dependency |

---

## 1. STUDENT Role

### 1.1 Authentication & Session

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| Register | `/register` | `POST /auth/register` | Public | **COMPLETE AND VERIFIED** |
| Login with role redirect | `/login` | `POST /auth/login` | Public | **COMPLETE AND VERIFIED** |
| Logout (clears session) | AppShell | `POST /auth/logout` | Authenticated | **COMPLETE AND VERIFIED** |
| Forgot password | `/forgot-password` | `POST /auth/forgot-password` | Public | **COMPLETE AND VERIFIED** |
| Reset password | `/reset-password` | `POST /auth/reset-password` | Public | **COMPLETE AND VERIFIED** |
| Verify email | `/verify-email` | `POST /auth/verify-email` | Public | **COMPLETE AND VERIFIED** |
| Session refresh (JWT rotation) | Automatic | `POST /auth/refresh` | Authenticated | **COMPLETE AND VERIFIED** |

### 1.2 Student Dashboard

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| Personalized welcome | `/dashboard` → StudentDashboard | `GET /dashboard` | Authenticated | **COMPLETE AND VERIFIED** |
| Unread notification count | `/dashboard` | `GET /dashboard` | Authenticated | **COMPLETE AND VERIFIED** |
| Bookmarked resource count | `/dashboard` | `GET /dashboard` | Authenticated | **COMPLETE AND VERIFIED** |
| Recent print orders list | `/dashboard` | `GET /dashboard` | Authenticated | **COMPLETE AND VERIFIED** |
| Recent resources list | `/dashboard` | `GET /dashboard` | Authenticated | **COMPLETE AND VERIFIED** |
| Quick action cards (SVG icons) | `/dashboard` | None (navigation) | Authenticated | **COMPLETE AND VERIFIED** |
| Ad banner (institution-scoped) | `/dashboard` | `GET /ads/serve` | Authenticated | **IMPLEMENTED BUT NOT VERIFIED** |
| Email verification warning | `/dashboard` | None (from /me) | Authenticated | **COMPLETE AND VERIFIED** |
| New user getting-started card | `/dashboard` | None (conditional) | Authenticated | **COMPLETE AND VERIFIED** |

### 1.3 Academic Resources

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| Browse resources (search + filter) | `/resources` | `GET /search` | Public | **COMPLETE AND VERIFIED** |
| Filter by university | `/resources` | `GET /institutions` | Public | **COMPLETE AND VERIFIED** |
| Filter by resource type | `/resources` | `GET /categories` | Public | **COMPLETE AND VERIFIED** |
| Filter by price (free/premium) | `/resources` | `GET /search` | Public | **COMPLETE AND VERIFIED** |
| Filter by course | `/resources?course_id=X` | `GET /search` | Public | **COMPLETE AND VERIFIED** |
| Sort by (newest, title A-Z, relevance) | `/resources` | `GET /search` | Public | **COMPLETE AND VERIFIED** |
| Pagination | `/resources` | `GET /search` | Public | **COMPLETE AND VERIFIED** |
| Resource detail page | `/resources/:id` | `GET /resources/{id}` | Public | **COMPLETE AND VERIFIED** |
| Free resource download | `/resources/:id` | `POST /resources/{id}/download` | Authenticated | **COMPLETE AND VERIFIED** |
| Premium resource: buy / payment | `/resources/:id` | `POST /payments` | `order:create` | **IMPLEMENTED BUT NOT VERIFIED** |
| Premium resource: blocked without entitlement | `/resources/:id` | `GET /resources/{id}` | Authenticated | **COMPLETE AND VERIFIED** |
| Resource status/access badges | `/resources/:id` | From resource data | Public | **COMPLETE AND VERIFIED** |
| Course tags (linked to filter) | `/resources/:id` | From resource data | Public | **COMPLETE AND VERIFIED** |
| Provider and institution info | `/resources/:id` | From resource data | Public | **COMPLETE AND VERIFIED** |
| Preview text | `/resources/:id` | From resource data | Public | **COMPLETE AND VERIFIED** |
| Bookmark / unbookmark | `/resources/:id` | `PUT/DELETE /bookmarks/{id}` | Authenticated | **COMPLETE AND VERIFIED** |
| Browse courses (catalog) | `/catalog` | `GET /faculties`, `/programs`, `/courses` | Public | **COMPLETE AND VERIFIED** |
| Filter catalog by faculty / programme | `/catalog` | `GET /programs`, `/courses` | Public | **COMPLETE AND VERIFIED** |
| Saved resources page | `/bookmarks` | `GET /bookmarks` | Authenticated | **COMPLETE AND VERIFIED** |

### 1.4 Printing Services

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| Choose university + print shop | `/print` | `GET /institutions`, `GET /print/shops` | `order:create` | **COMPLETE AND VERIFIED** |
| Upload document | `/print` | `POST /print/documents` | `order:create` | **COMPLETE AND VERIFIED** |
| Configure copies, paper, colour, duplex | `/print` | From pricing data | `order:create` | **COMPLETE AND VERIFIED** |
| Server-side price quote | `/print` | `POST /print/orders/quote` | `order:create` | **COMPLETE AND VERIFIED** |
| Pay on pickup | `/print` | `POST /print/orders` | `order:create` | **COMPLETE AND VERIFIED** |
| Pay online (FakeProvider dev only) | `/print` | `POST /payments` | `order:create` | **IMPLEMENTED BUT NOT VERIFIED** |
| Submit print order | `/print` | `POST /print/orders` | `order:create` | **COMPLETE AND VERIFIED** |
| View all orders | `/print/orders` | `GET /print/orders` | `order:read` | **COMPLETE AND VERIFIED** |
| View order detail | `/print/orders/:id` | `GET /print/orders/{id}` | `order:read` | **COMPLETE AND VERIFIED** |
| Pickup code display | `/print/orders/:id` | From order data | `order:read` | **COMPLETE AND VERIFIED** |
| Order history / progress timeline | `/print/orders/:id` | From order data | `order:read` | **COMPLETE AND VERIFIED** |
| Cancel order (while SUBMITTED) | `/print/orders/:id` | `POST /print/orders/{id}/cancel` | `order:read` | **COMPLETE AND VERIFIED** |
| Pay now (unpaid online orders) | `/print/orders/:id` | `POST /payments` | `order:read` | **IMPLEMENTED BUT NOT VERIFIED** |
| Auto-refresh active orders (20s) | `/print/orders/:id` | `GET /print/orders/{id}` | `order:read` | **COMPLETE AND VERIFIED** |

### 1.5 Notifications

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| View all notifications | `/notifications` | `GET /notifications` | Authenticated | **COMPLETE AND VERIFIED** |
| Mark individual notification read | `/notifications` | `POST /notifications/read` | Authenticated | **COMPLETE AND VERIFIED** |
| Mark all read | `/notifications` | `POST /notifications/read-all` | Authenticated | **COMPLETE AND VERIFIED** |
| Notification bell with unread count | AppShell | `GET /notifications/unread-count` | Authenticated | **COMPLETE AND VERIFIED** |
| Bell dropdown preview (last 10) | AppShell | `GET /notifications` | Authenticated | **COMPLETE AND VERIFIED** |
| Navigate to related item from notification | `/notifications` | None (action_url from API) | Authenticated | **COMPLETE AND VERIFIED** |
| Pagination | `/notifications` | `GET /notifications` | Authenticated | **COMPLETE AND VERIFIED** |

### 1.6 Account & Profile

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| View profile | `/account` | `GET /me` | Authenticated | **COMPLETE AND VERIFIED** |
| Edit full name + phone | `/account` | `PATCH /me` | Authenticated | **COMPLETE AND VERIFIED** |
| View student profile (read-only) | `/account` | From /me | Authenticated | **COMPLETE AND VERIFIED** |
| View assigned roles | `/account` | From /me | Authenticated | **COMPLETE AND VERIFIED** |
| Change password | `/account` | `POST /auth/change-password` | Authenticated | **COMPLETE AND VERIFIED** |
| Sign out | AppShell / `/account` | `POST /auth/logout` | Authenticated | **COMPLETE AND VERIFIED** |
| Email verification status | `/account` | From /me | Authenticated | **COMPLETE AND VERIFIED** |

### 1.7 Help & Support

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| FAQ accordion (10 questions) | `/help` | None (static) | Authenticated | **COMPLETE AND VERIFIED** |
| Provider FAQ section | `/help` | None (static) | Authenticated | **COMPLETE AND VERIFIED** |
| Operator FAQ section | `/help` | None (static) | Authenticated | **COMPLETE AND VERIFIED** |
| Support contact info | `/help` | None (static) | Authenticated | **COMPLETE AND VERIFIED** |
| System status link | `/help` | None (links to /status) | Authenticated | **COMPLETE AND VERIFIED** |

### 1.8 Navigation (Student)

| Item | Destination | Status |
|---|---|---|
| Dashboard | `/dashboard` | **COMPLETE AND VERIFIED** |
| Resources | `/resources` | **COMPLETE AND VERIFIED** |
| Courses | `/catalog` | **COMPLETE AND VERIFIED** |
| Saved | `/bookmarks` | **COMPLETE AND VERIFIED** |
| New print order | `/print` | **COMPLETE AND VERIFIED** |
| My orders | `/print/orders` | **COMPLETE AND VERIFIED** |
| Notifications | `/notifications` | **COMPLETE AND VERIFIED** |
| Account | `/account` | **COMPLETE AND VERIFIED** |
| Help | `/help` | **COMPLETE AND VERIFIED** |

---

## 2. RESOURCE_PROVIDER Role

### 2.1 Provider Dashboard

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| Provider welcome card | `/provider/dashboard` | `GET /dashboard` | `resource:create` | **COMPLETE AND VERIFIED** |
| Resource counts (total, published, pending, rejected) | `/provider/dashboard` | Custom stats endpoint | `resource:create` | **IMPLEMENTED BUT NOT VERIFIED** |
| Recent submissions list | `/provider/dashboard` | `GET /dashboard` | `resource:create` | **COMPLETE AND VERIFIED** |
| Publishing workflow explanation | `/provider/dashboard` | None (static) | `resource:create` | **COMPLETE AND VERIFIED** |
| Upload CTA (empty state) | `/provider/dashboard` | None (navigation) | `resource:create` | **COMPLETE AND VERIFIED** |

### 2.2 Resource Management

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| List my resources | `/provider/resources` | `GET /resources/mine` | `resource:create` | **COMPLETE AND VERIFIED** |
| Filter by status | `/provider/resources` | `GET /resources/mine?status=X` | `resource:create` | **COMPLETE AND VERIFIED** |
| Pagination | `/provider/resources` | `GET /resources/mine` | `resource:create` | **COMPLETE AND VERIFIED** |
| Create new resource (form) | `/provider/resources/new` | `POST /resources` | `resource:create` | **IMPLEMENTED BUT NOT VERIFIED** |
| Edit resource (title, desc, category) | `/provider/resources/:id` | `PATCH /resources/{id}` | `resource:create` | **IMPLEMENTED BUT NOT VERIFIED** |
| Upload resource file | `/provider/resources/:id` | `POST /resources/{id}/versions` | `resource:create` | **IMPLEMENTED BUT NOT VERIFIED** |
| Submit for review | `/provider/resources/:id` | `POST /resources/{id}/submit` | `resource:create` | **IMPLEMENTED BUT NOT VERIFIED** |
| View rejection feedback | `/provider/resources/:id` | From resource data | `resource:create` | **IMPLEMENTED BUT NOT VERIFIED** |
| Delete draft | `/provider/resources` | `DELETE /resources/{id}` | `resource:create` | **COMPLETE AND VERIFIED** |
| Resource status display | `/provider/resources` | From resource data | `resource:create` | **COMPLETE AND VERIFIED** |

### 2.3 Resource Moderation Workflow (Provider View)

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| View moderation queue | `/moderation` | `GET /resources?status=SUBMITTED` | `resource:review` | **IMPLEMENTED BUT NOT VERIFIED** |
| Approve resource | `/moderation` | `POST /resources/{id}/approve` | `resource:review` | **IMPLEMENTED BUT NOT VERIFIED** |
| Reject resource with reason | `/moderation` | `POST /resources/{id}/reject` | `resource:review` | **IMPLEMENTED BUT NOT VERIFIED** |

### 2.4 Navigation (Provider)

| Item | Destination | Status |
|---|---|---|
| Dashboard | `/provider/dashboard` | **COMPLETE AND VERIFIED** |
| My resources | `/provider/resources` | **COMPLETE AND VERIFIED** |
| Upload resource | `/provider/resources/new` | **COMPLETE AND VERIFIED** |
| Moderation | `/moderation` | **COMPLETE AND VERIFIED** |
| Notifications | `/notifications` | **COMPLETE AND VERIFIED** |
| Account | `/account` | **COMPLETE AND VERIFIED** |
| Help | `/help` | **COMPLETE AND VERIFIED** |

---

## 3. PRINTING_OPERATOR Role

### 3.1 Operator Dashboard

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| Operator welcome card + new order count badge | `/operator/dashboard` | Custom stats | `order:read_any` | **IMPLEMENTED BUT NOT VERIFIED** |
| Queue stats (submitted/accepted/printing/ready) | `/operator/dashboard` | Custom stats | `order:read_any` | **IMPLEMENTED BUT NOT VERIFIED** |
| New orders list (top 5, auto-refresh 30s) | `/operator/dashboard` | `GET /operator/orders?status=SUBMITTED` | `order:read_any` | **IMPLEMENTED BUT NOT VERIFIED** |
| Quick access grid (4 status links) | `/operator/dashboard` | None (navigation) | `order:read_any` | **COMPLETE AND VERIFIED** |

### 3.2 Print Queue

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| List orders (all statuses) | `/operator` | `GET /operator/orders` | `order:read_any` | **COMPLETE AND VERIFIED** |
| Filter by shop | `/operator` | `GET /operator/orders?shop_id=X` | `order:read_any` | **COMPLETE AND VERIFIED** |
| Filter by status | `/operator` | `GET /operator/orders?status=X` | `order:read_any` | **COMPLETE AND VERIFIED** |
| Auto-refresh every 30 s | `/operator` | `GET /operator/orders` | `order:read_any` | **COMPLETE AND VERIFIED** |
| Pagination | `/operator` | `GET /operator/orders` | `order:read_any` | **COMPLETE AND VERIFIED** |
| "Not assigned to shop" alert | `/operator` | `GET /operator/shops` | `order:read_any` | **COMPLETE AND VERIFIED** |

### 3.3 Order Detail & State Machine

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| Order detail view | `/operator/orders/:id` | `GET /operator/orders/{id}` | `order:read_any` | **COMPLETE AND VERIFIED** |
| Open customer document (signed URL) | `/operator/orders/:id` | `POST /operator/orders/{id}/items/{item_id}/document-link` | `order:read_any` | **COMPLETE AND VERIFIED** |
| Accept order | `/operator/orders/:id` | `POST /operator/orders/{id}/accept` | `order:update_status` | **COMPLETE AND VERIFIED** |
| Reject order (with reason) | `/operator/orders/:id` | `POST /operator/orders/{id}/reject` | `order:update_status` | **COMPLETE AND VERIFIED** |
| Start printing | `/operator/orders/:id` | `POST /operator/orders/{id}/printing` | `order:update_status` | **COMPLETE AND VERIFIED** |
| Mark ready for pickup | `/operator/orders/:id` | `POST /operator/orders/{id}/ready` | `order:update_status` | **COMPLETE AND VERIFIED** |
| Record cash payment | `/operator/orders/:id` | `POST /operator/orders/{id}/payment` | `payment:record_cash` | **COMPLETE AND VERIFIED** |
| Confirm pickup (validate code) | `/operator/orders/:id` | `POST /operator/orders/{id}/complete` | `order:update_status` | **COMPLETE AND VERIFIED** |
| Retention hold toggle | `/operator/orders/:id` | `POST /operator/orders/{id}/hold` | `order:manage_any` | **COMPLETE AND VERIFIED** |
| Wrong-code error from server | `/operator/orders/:id` | 403 from complete endpoint | `order:update_status` | **COMPLETE AND VERIFIED** |
| "Payment required" for online orders | `/operator/orders/:id` | From order data | `order:read_any` | **COMPLETE AND VERIFIED** |
| Deleted document fallback message | `/operator/orders/:id` | From item data | `order:read_any` | **COMPLETE AND VERIFIED** |

### 3.4 Navigation (Operator)

| Item | Destination | Status |
|---|---|---|
| Dashboard | `/operator/dashboard` | **COMPLETE AND VERIFIED** |
| Print queue | `/operator` | **COMPLETE AND VERIFIED** |
| Notifications | `/notifications` | **COMPLETE AND VERIFIED** |
| Account | `/account` | **COMPLETE AND VERIFIED** |
| Help | `/help` | **COMPLETE AND VERIFIED** |

---

## 4. ADMIN Role

### 4.1 Admin Dashboard

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| Admin welcome card | `/admin` → AdminDashboard | `GET /dashboard` | `user:read` | **IMPLEMENTED BUT NOT VERIFIED** |
| Platform metrics (users, resources, orders, ads) | `/admin` → AdminDashboard | `GET /admin/analytics` | `user:read` | **IMPLEMENTED BUT NOT VERIFIED** |
| Section deep-link cards (URL param tabs) | `/admin` → AdminDashboard | None (navigation) | `user:read` | **COMPLETE AND VERIFIED** |

### 4.2 User Management

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| List users (paginated) | `/admin?tab=users` | `GET /admin/users` | `user:read` | **COMPLETE AND VERIFIED** |
| Search users | `/admin?tab=users` | `GET /admin/users?q=X` | `user:read` | **COMPLETE AND VERIFIED** |
| View roles + account status | `/admin?tab=users` | From user list | `user:read` | **COMPLETE AND VERIFIED** |
| Suspend user (with reason) | `/admin?tab=users` | `POST /admin/users/{id}/suspend` | `user:suspend` | **COMPLETE AND VERIFIED** |
| Reinstate user | `/admin?tab=users` | `POST /admin/users/{id}/reinstate` | `user:suspend` | **COMPLETE AND VERIFIED** |
| Grant role | `/admin?tab=users` | `POST /admin/users/{id}/roles` | `role:grant` | **COMPLETE AND VERIFIED** |
| Revoke role | `/admin?tab=users` | `DELETE /admin/users/{id}/roles/{role}` | `role:grant` | **COMPLETE AND VERIFIED** |

### 4.3 Institution Management

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| List institutions | `/admin?tab=institutions` | `GET /institutions` | `institution:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| Create institution | `/admin?tab=institutions` | `POST /institutions` | `institution:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| Edit institution (name, code) | `/admin?tab=institutions` | `PATCH /institutions/{id}` | `institution:manage` | **IMPLEMENTED BUT NOT VERIFIED** |

### 4.4 Academic Structure Management

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| List/create/edit faculties | `/admin?tab=academic` | `GET/POST/PATCH /faculties` | `catalog:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| Activate/deactivate faculties | `/admin?tab=academic` | `PATCH /faculties/{id}` | `catalog:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| List/create/edit programmes | `/admin?tab=academic` | `GET/POST/PATCH /programs` | `catalog:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| Activate/deactivate programmes | `/admin?tab=academic` | `PATCH /programs/{id}` | `catalog:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| List/search/create/edit courses | `/admin?tab=academic` | `GET/POST/PATCH /courses` | `catalog:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| Activate/deactivate courses | `/admin?tab=academic` | `PATCH /courses/{id}` | `catalog:manage` | **IMPLEMENTED BUT NOT VERIFIED** |

### 4.5 Resource Moderation

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| Moderation queue (tab link) | `/admin?tab=moderation` → `/moderation` | `GET /resources?status=SUBMITTED` | `resource:review` | **IMPLEMENTED BUT NOT VERIFIED** |
| View submitted resource detail | `/moderation` | `GET /resources/{id}` | `resource:review` | **IMPLEMENTED BUT NOT VERIFIED** |
| Approve resource | `/moderation` | `POST /resources/{id}/approve` | `resource:review` | **IMPLEMENTED BUT NOT VERIFIED** |
| Reject with reason | `/moderation` | `POST /resources/{id}/reject` | `resource:review` | **IMPLEMENTED BUT NOT VERIFIED** |

### 4.6 Printing Management

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| All orders (filter by status) | `/admin?tab=printing` | `GET /admin/orders` | `order:read_any` | **COMPLETE AND VERIFIED** |
| View order detail link | `/admin?tab=printing` | Links to `/operator/orders/:id` | `order:read_any` | **COMPLETE AND VERIFIED** |
| List shops (inc. inactive) | `/admin?tab=printing` | `GET /print/shops?include_inactive=true` | `printshop:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| Create shop | `/admin?tab=printing` | `POST /print/shops` | `printshop:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| Edit shop (name, location, pay-on-pickup) | `/admin?tab=printing` | `PATCH /print/shops/{id}` | `printshop:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| Activate / deactivate shop | `/admin?tab=printing` | `PATCH /print/shops/{id}` | `printshop:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| View shop pricing rules | `/admin?tab=printing` | `GET /print/shops/{id}/pricing` | `printshop:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| Add pricing rule | `/admin?tab=printing` | `POST /print/shops/{id}/pricing` | `printshop:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| Activate/deactivate pricing rule | `/admin?tab=printing` | `PATCH /print/shops/{id}/pricing/{rid}` | `printshop:manage` | **IMPLEMENTED BUT NOT VERIFIED** |

### 4.7 Notifications / Outbox

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| Outbox processing trigger | `/admin?tab=notifications` | `POST /notifications/process-outbox` | `analytics:read` | **IMPLEMENTED BUT NOT VERIFIED** |

### 4.8 Audit Log

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| Paginated audit log | `/admin?tab=audit` | `GET /admin/audit-log` | `audit:read` | **COMPLETE AND VERIFIED** |
| Filter by action type | `/admin?tab=audit` | `GET /admin/audit-log?action=X` | `audit:read` | **COMPLETE AND VERIFIED** |

### 4.9 Advertising

| Feature | Route/Page | Backend API | Permission | Status |
|---|---|---|---|---|
| List advertisers | `/admin?tab=advertising` | `GET /ads/advertisers` | `advertisement:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| Create advertiser | `/admin?tab=advertising` | `POST /ads/advertisers` | `advertisement:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| List campaigns | `/admin?tab=advertising` | `GET /ads/campaigns` | `advertisement:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| Create campaign | `/admin?tab=advertising` | `POST /ads/campaigns` | `advertisement:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| Edit campaign (name, dates, active) | `/admin?tab=advertising` | `PATCH /ads/campaigns/{id}` | `advertisement:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| List advertisements | `/admin?tab=advertising` | `GET /ads` | `advertisement:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| Create advertisement | `/admin?tab=advertising` | `POST /ads` | `advertisement:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| Activate / pause / archive ad | `/admin?tab=advertising` | `PATCH /ads/{id}/status` | `advertisement:manage` | **IMPLEMENTED BUT NOT VERIFIED** |
| Ad metrics per advertisement | `/admin?tab=advertising` | `GET /ads/{id}/metrics` | `advertisement:manage` | **IMPLEMENTED BUT NOT VERIFIED** |

### 4.10 Navigation (Admin)

| Item | Destination | Status |
|---|---|---|
| Admin dashboard | `/admin` | **COMPLETE AND VERIFIED** |
| Moderation | `/moderation` | **COMPLETE AND VERIFIED** |
| Resources | `/resources` | **COMPLETE AND VERIFIED** |
| Notifications | `/notifications` | **COMPLETE AND VERIFIED** |
| Account | `/account` | **COMPLETE AND VERIFIED** |
| Help | `/help` | **COMPLETE AND VERIFIED** |
| Admin panel → Users tab | `/admin?tab=users` | **COMPLETE AND VERIFIED** |
| Admin panel → Institutions tab | `/admin?tab=institutions` | **COMPLETE AND VERIFIED** |
| Admin panel → Academic tab | `/admin?tab=academic` | **COMPLETE AND VERIFIED** |
| Admin panel → Printing tab | `/admin?tab=printing` | **COMPLETE AND VERIFIED** |
| Admin panel → Advertising tab | `/admin?tab=advertising` | **COMPLETE AND VERIFIED** |
| Admin panel → Audit log tab | `/admin?tab=audit` | **COMPLETE AND VERIFIED** |

---

## 5. Shared / Cross-Role Features

| Feature | Roles | Backend API | Status |
|---|---|---|---|
| Theme toggle (light/dark) | All | None (localStorage) | **COMPLETE AND VERIFIED** |
| Offline banner | All | None (navigator.onLine) | **COMPLETE AND VERIFIED** |
| PWA installability | All | Service worker (Workbox) | **COMPLETE AND VERIFIED** |
| PWA offline fallback | All | Service worker cache | **IMPLEMENTED BUT NOT VERIFIED** |
| System status page | All | `GET /health` | **COMPLETE AND VERIFIED** |
| 404 page with quick links | All | None | **COMPLETE AND VERIFIED** |
| Route error boundary | All | None | **COMPLETE AND VERIFIED** |
| Ad banner (AdBanner component) | Student | `GET /ads/serve` | **IMPLEMENTED BUT NOT VERIFIED** |

---

## 6. Known Gaps and Outstanding Items

| Item | Severity | Notes |
|---|---|---|
| E2E tests (Playwright) | Medium | 2 spec files exist; require live backend + PostgreSQL to run |
| Backend integration tests | High | 470 collected; require PostgreSQL (unavailable locally) |
| Real payment provider | High (production) | Only FakeProvider; pay-on-pickup is production workflow |
| Real email provider | High (production) | ConsoleEmailSender / DisabledEmailSender in production |
| Malware scanning | Medium | NoopScanner — uploaded files are not scanned |
| Multi-instance rate limiting | Low | In-process only; needs Redis for horizontal scaling |
| Provider stats endpoint verification | Low | Stats computed from /resources/mine client-side aggregation |
| Operator stats endpoint verification | Low | Stats computed from /operator/orders aggregation |
| Ad banner real impression tracking | Low | Frontend fires impression event; needs live DB to verify |

---

*Generated by Kiro Code Agent — 25 November 2026*
