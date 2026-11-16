# Academic structure, resources, premium access and search (Phases 5-7)

Status: implemented, **not yet executed** (see "Verification status").

## Academic hierarchy

`institutions -> faculties -> departments -> programs -> courses`, plus `program_courses` (many-to-many).
Universities name things differently, so `faculties.kind` is FACULTY / SCHOOL / COLLEGE / INSTITUTE, and programs
and courses may sit directly under a faculty (`department_id` NULL).

**Isolation is enforced by the database.** Every level carries `institution_id`, and composite foreign keys force a
child's institution to equal its parent's (e.g. `departments (faculty_id, institution_id) -> faculties (id, institution_id)`).
A department cannot reference another university's faculty, a course cannot be linked to another university's program,
and a resource can only be linked to courses of its own institution (`course_resources`) even if application code is wrong.

Administration needs `catalog:manage` for that institution. Objects outside the caller's scope return 404.
Creating institutions is platform-level (`institution:manage`). Listing/reading the catalogue is public.

## Resources

`resources` (institution-owned, provider-owned), `resource_versions` (history is never overwritten; exactly one
version may be `is_current`, enforced by a partial unique index), `resource_categories` (a table, so new types need no
code change; seeded: notes, past papers, handouts, study guides, reference material, academic documents), `tags`,
`resource_tags`, `course_resources`, `resource_reviews` (append-only history of every lifecycle decision, with reasons),
`entitlements`, `bookmarks`, `resource_downloads` (download log), `stored_files` (file metadata).
Money is integer UGX with a check constraint: PREMIUM needs a price > 0, FREE must have none.

### Lifecycle

`DRAFT -> SUBMITTED -> UNDER_REVIEW -> APPROVED -> PUBLISHED -> ARCHIVED`, and `UNDER_REVIEW -> REJECTED -> DRAFT`.
Rejection needs a reason (also a DB check). Editing or uploading to a REJECTED resource reopens it as DRAFT.
Archived resources can be re-published by staff. Publishing marks the newest version as the explicit current version.

| Action | Who (permission, scoped to the resource's institution) |
|---|---|
| create / edit / upload / submit / delete draft | the owning provider (`resource:create/update/submit/delete`) |
| start review, approve, reject | `resource:review` |
| publish | `resource:publish` |
| archive | owner (`resource:delete`) or `resource:publish` |

**Separation of duties:** nobody reviews or publishes their own resource unless they hold `resource:review_own`.
No default role holds it (ADMIN is deliberately excluded), so granting it needs a separately created role.

## Access and downloads

`POST /resources/{id}/download` decides, in order: authenticated -> exists -> visible (published, or owner / in-scope staff)
-> free, or active entitlement, or owner/staff override -> a file exists and is not INFECTED. Only then does it log the
download and return a link. Premium is enforced here, never by hiding things in the UI.

* **Link:** with local storage the API mints a 60-second signed token bound to one user and one file and serves
  `GET /downloads/{token}` (streamed, `attachment`, `nosniff`). With S3 it returns a presigned URL. Storage keys are never
  serialised. A suspended user's link stops working; an infected file's link stops working.
* **Entitlements:** one row per (user, resource); revoke sets REVOKED and re-grant reactivates it. Source is PURCHASE,
  ADMIN_GRANT or PROMO. Until the payments phase, access is granted by staff with `entitlement:manage`
  (`POST /resources/{id}/entitlements`); the payments phase will call the same service with source PURCHASE.
* **Public vs private:** published resources' metadata, price and preview text are public; files and unpublished
  resources are not (unpublished resources return 404 to everyone but the owner and in-scope staff).

## Upload security

Size is capped while streaming (default 25 MB, also an early Content-Length check); type is decided by **magic bytes**
against an allow-list (PDF, DOCX, PPTX, XLSX, PNG, JPEG, plain text). Executables, scripts, HTML/SVG/XML, legacy Office
files and OOXML with macros are rejected. The client's filename and MIME type are ignored: the stored key is generated and
the display name is sanitised with the detected extension. Every upload passes a `MalwareScanner` hook (currently a no-op
that records NOT_SCANNED) before storage is written. Infected files are never served.

## Search

PostgreSQL only. Full-text search runs on a database-maintained `tsvector` (title + description, GIN-indexed), combined with
course-code prefix matching (any spelling: `MTH1101`, `mth 1101`), exact tag match and title substring, ranked by
`ts_rank_cd` plus boosts. Filters: institution, faculty, department, program, course, category, tag, access, year.
Sort: relevance / newest / title. Offset pagination (max 50 per page) with `meta.total`. Only PUBLISHED resources are
ever returned. LIKE wildcards in user input are escaped.

## Endpoints (all under `/api/v1`)

Catalogue: `GET /institutions[/{id}]`, `/faculties`, `/departments`, `/programs`, `/courses` (public);
`POST`/`PATCH` on each (catalog:manage), `POST /programs/{id}/courses`, `POST`/`PATCH /institutions`.
Resources: `GET /resources`, `GET /search`, `GET /resources/{id}`, `POST /resources`, `PATCH`, `DELETE` (draft),
`POST /resources/{id}/versions` (multipart), `/submit`, `/start-review`, `/approve`, `/reject`, `/publish`, `/archive`,
`/download`, `GET /resources/{id}/stats`, `GET /resources/mine`, `GET /resources/review-queue`,
`POST|DELETE /resources/{id}/entitlements`. Bookmarks: `GET /bookmarks`, `PUT|DELETE /bookmarks/{id}` (own only; no user id anywhere).
Reference: `GET|POST /categories`, `GET /tags?q=`. Files: `GET /downloads/{token}`.

## Frontend

`/resources` (search + filters, URL-synced, paginated 12 per page, nothing is fetched while typing), `/resources/:id`
(detail, preview, free download, premium access screen, bookmark, moderation panel), `/catalog` (university -> faculty ->
program -> courses), `/bookmarks`, `/provider/resources[/new|/:id]`, `/moderation`. Route guards and hidden buttons are UX only;
the API re-checks everything.

## Demo data and E2E

`python -m app.cli seed-demo` (refuses in production) creates a student, provider and Makerere-scoped admin
(`*@demo.oars.test`, password `Demo-password-123`), a small academic tree and one free and one premium published resource.
`cd frontend && npm run e2e` uses its own database `oars_e2e` and storage folder (create the database once on an existing
Postgres volume: `docker compose exec postgres psql -U oars -d oars -c "CREATE DATABASE oars_e2e;"`), runs migrations and the
seed, starts both servers on ports 8001/5174, and needs `npx playwright install chromium` once and the backend venv active.

## Decisions and limitations

* **Purchase now exists (Phase 9)** through the payment abstraction (FakeProvider only); see `docs/printing-payments.md`. In production the Buy button is hidden and the screen says online purchase isn't available until a real provider is configured.
* **Preview** is provider-written text, not a rendered page of the file (PDF page rendering is deferred).
* Publishing a new version of an already-published resource is not supported (versions can be added only while DRAFT or
  REJECTED); updating published content needs a re-review design.
* Search has no typo tolerance (no `pg_trgm`) and uses offset pagination; fine for MVP volumes, revisit with scale.
* `S3Storage` is written but untested here; it needs `pip install '.[s3]'` and a browser-reachable endpoint for presigned URLs.
* Malware scanning is a hook only. A failed blob delete after a draft is removed can leave an orphan file (logged).
* Student profile program selection (`student_profiles.program_id`) has its foreign key but no endpoint/UI yet.
* No mobile bottom navigation or offline caching of the catalogue yet (Phase 13).
* The E2E suite is not part of CI.

## Verification status

Written and statically cross-checked (imports resolve; 27 tables and all indexes agree between models and migrations) but
**not executed**: no database, pytest, npm, ruff, mypy, tsc, eslint, vitest, build or Playwright run has happened.
