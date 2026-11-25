# OARS Role Dashboard — Implementation Plan

**Tracking document for the dashboard, page completion, and role-separation work.**
**Last updated:** 25 November 2026

---

## Legend

| Symbol | Meaning |
|---|---|
| ✅ Verified complete | Implemented, TypeScript clean, build passes |
| 🔨 Implemented | Code written and linting/build confirmed |
| ⚠️ Partial | Exists but incomplete |
| ❌ Not started | Missing |
| 🚫 Blocked | Cannot proceed without external dependency |

---

## 0. Role Separation Architecture

| Item | Status | Files | Notes |
|---|---|---|---|
| `useRole()` hook | ✅ | `src/features/auth/use-role.ts` | Priority: ADMIN > RESOURCE_PROVIDER > PRINTING_OPERATOR > STUDENT |
| `roleDashboardPath()` | ✅ | `src/features/auth/use-role.ts` | Used by LoginPage for post-login redirect |
| `canAny()` | ✅ | `src/features/auth/auth-context.ts`, `AuthProvider.tsx` | Institution-scoped permission checks |
| `refreshMe()` | ✅ | `src/features/auth/auth-context.ts`, `AuthProvider.tsx` | Refreshes auth state after profile update |
| Role-specific nav configs | ✅ | `src/app/nav-config.ts` | STUDENT_NAV, PROVIDER_NAV, OPERATOR_NAV, ADMIN_NAV |
| AppShell role-based nav | ✅ | `src/app/AppShell.tsx` | Renders only current role's nav + role badge |
| DashboardPage dispatcher | ✅ | `src/features/dashboard/DashboardPage.tsx` | Student → StudentDashboard; others redirect |
| StudentDashboard | ✅ | `src/features/dashboard/StudentDashboard.tsx` | Academic-focused |
| ProviderDashboard | ✅ | `src/features/dashboard/ProviderDashboard.tsx` | Resource stats + submissions |
| OperatorDashboard | ✅ | `src/features/dashboard/OperatorDashboard.tsx` | Queue stats + new orders |
| AdminDashboard | ✅ | `src/features/dashboard/AdminDashboard.tsx` | Platform metrics + admin tools |
| LoginPage role-specific redirect | ✅ | `src/features/auth/LoginPage.tsx` | Redirects to `roleDashboardPath(role)` |
| RequirePermission uses canAny | ✅ | `src/features/auth/RequireAuth.tsx` | Fixes institution-scoped permission gating |
| AdminPage tabs use canAny | ✅ | `src/features/admin/AdminPage.tsx` | All tab visibility checks |

---

## 1. Student

| Route | Page | Status |
|---|---|---|
| `/` | Home / landing | ✅ |
| `/login` | Login (role-specific redirect) | ✅ |
| `/register` | Register | ✅ |
| `/forgot-password` | Forgot password | ✅ |
| `/reset-password` | Reset password | ✅ |
| `/verify-email` | Email verification | ✅ |
| `/dashboard` | **StudentDashboard** (role-specific) | ✅ |
| `/account` | Account / profile editing | ✅ |
| `/resources` | Browse resources | ✅ |
| `/resources/:id` | Resource detail | ✅ |
| `/catalog` | Browse courses | ✅ |
| `/bookmarks` | Saved resources | ✅ |
| `/notifications` | Notifications | ✅ |
| `/print` | New print order | ✅ |
| `/print/orders` | Order history | ✅ |
| `/print/orders/:id` | Order detail | ✅ |
| `/payments/:id` | Payment return | ✅ |
| `/help` | Help & support | ✅ |

**Student completion: 100%**

---

## 2. Resource Provider

| Route | Page | Status |
|---|---|---|
| `/provider/dashboard` | **ProviderDashboard** | ✅ |
| `/provider/resources` | My resources (with delete-draft) | ✅ |
| `/provider/resources/new` | Create resource | ✅ |
| `/provider/resources/:id` | Edit / upload / submit | ✅ |
| `/moderation` | Moderation queue (if reviewer) | ✅ |
| `/notifications` | Notifications | ✅ |
| `/account` | Account with profile editing | ✅ |
| `/help` | Help | ✅ |

**Provider completion: 100%**

---

## 3. Printing Operator

| Route | Page | Status |
|---|---|---|
| `/operator/dashboard` | **OperatorDashboard** | ✅ |
| `/operator` | Print queue (URL-driven status filter) | ✅ |
| `/operator/orders/:id` | Order detail + state machine | ✅ |
| `/notifications` | Notifications | ✅ |
| `/account` | Account with profile editing | ✅ |
| `/help` | Help | ✅ |

**Operator completion: 100%**

---

## 4. Admin

| Route / Tab | Status |
|---|---|
| `/admin` → Overview | ✅ |
| `/admin` → Users | ✅ |
| `/admin` → Institutions | ✅ |
| `/admin` → Academic | ✅ **Full CRUD — faculties, programs, courses** |
| `/admin` → Moderation | ✅ |
| `/admin` → Printing → Orders | ✅ |
| `/admin` → Printing → Shop management | ✅ **NEW — create, edit, activate/deactivate, pricing rules** |
| `/admin` → Notifications | ✅ |
| `/admin` → Audit log | ✅ |
| `/admin` → Advertising | ✅ **Campaign list with inline editing** |

**Admin completion: 100%**

---

## 5. Navigation Configuration

| Role | Nav items | File |
|---|---|---|
| Student | Dashboard, Resources, Courses, Saved, New print order, My orders, Notifications, Help | `STUDENT_NAV` |
| Provider | Dashboard, My resources, Upload resource, Moderation, Notifications, Help | `PROVIDER_NAV` |
| Operator | Dashboard, Print queue, Notifications, Help | `OPERATOR_NAV` |
| Admin | Admin dashboard, Moderation, Resources, Notifications, Help | `ADMIN_NAV` |

---

## 6. Testing and Quality

| Check | MP9 Baseline | MP10 Final |
|---|---|---|
| TypeScript `tsc --noEmit` | ✅ 0 errors | ✅ 0 errors |
| ESLint | ✅ 0 errors | ✅ 0 errors |
| Vitest unit / integration | ✅ 192 passed | ✅ **192 passed** (26 test files) |
| Vite production build | ✅ 702 KB | ✅ **683 KB** + PWA SW |
| Backend tests | 470 collected, no PostgreSQL | 470 collected, no PostgreSQL |

---

## 7. Completed Work — Master Prompt 10

All identified gaps from MP9 have been closed:

| Item | MP9 Status | MP10 Status |
|---|---|---|
| Print shop management UI | ❌ Missing | ✅ Complete (`PrintShopPanel`) |
| Academic CRUD forms | ⚠️ Read-only placeholder | ✅ Complete (`AcademicManagementPanel`) |
| Campaign editing | ❌ Create only | ✅ Complete (inline `EditCampaignForm`) |
| Delete-draft UI | ❌ Missing | ✅ Complete (confirm dialog in `ProviderResourcesPage`) |
| Profile editing | ❌ Missing | ✅ Complete (all roles via `AccountPage`) |
| Backend `PATCH /me` | ❌ Missing | ✅ Complete (`ProfilePatch` schema + `update_me` service) |
| Backend `PATCH /ads/campaigns/{id}` | ❌ Missing | ✅ Complete (`CampaignPatch` schema + `update_campaign` service) |

---

*Updated by Kiro Code Agent — 25 November 2026*
