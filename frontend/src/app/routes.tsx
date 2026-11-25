import type { RouteObject } from "react-router-dom";
import { AppShell } from "@/app/AppShell";
import { NotFoundPage } from "@/app/NotFoundPage";
import { RouteErrorPage } from "@/app/RouteErrorPage";
import { AdminPage } from "@/features/admin/AdminPage";
import { AccountPage } from "@/features/auth/AccountPage";
import { ForgotPasswordPage } from "@/features/auth/ForgotPasswordPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { RequireAuth, RequirePermission } from "@/features/auth/RequireAuth";
import { ResetPasswordPage } from "@/features/auth/ResetPasswordPage";
import { VerifyEmailPage } from "@/features/auth/VerifyEmailPage";
import { CatalogPage } from "@/features/catalog/CatalogPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { ProviderDashboardPage } from "@/features/dashboard/ProviderDashboardPage";
import { OperatorDashboardPage } from "@/features/dashboard/OperatorDashboardPage";
import { HelpPage } from "@/features/help/HelpPage";
import { HomePage } from "@/features/home/HomePage";
import { NotificationsPage } from "@/features/notifications/NotificationsPage";
import { OperatorOrderPage } from "@/features/operator/OperatorOrderPage";
import { OperatorQueuePage } from "@/features/operator/OperatorQueuePage";
import { FakeCheckoutPage } from "@/features/payments/FakeCheckoutPage";
import { PaymentReturnPage } from "@/features/payments/PaymentReturnPage";
import { NewPrintOrderPage } from "@/features/printing/NewPrintOrderPage";
import { PrintOrderPage } from "@/features/printing/PrintOrderPage";
import { PrintOrdersPage } from "@/features/printing/PrintOrdersPage";
import { BookmarksPage } from "@/features/resources/BookmarksPage";
import { BrowsePage } from "@/features/resources/BrowsePage";
import { ModerationPage } from "@/features/resources/ModerationPage";
import { ProviderResourceFormPage } from "@/features/resources/ProviderResourceFormPage";
import { ProviderResourcesPage } from "@/features/resources/ProviderResourcesPage";
import { ResourceDetailPage } from "@/features/resources/ResourceDetailPage";

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    errorElement: <RouteErrorPage />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "login", element: <LoginPage /> },
      { path: "register", element: <RegisterPage /> },
      { path: "forgot-password", element: <ForgotPasswordPage /> },
      { path: "reset-password", element: <ResetPasswordPage /> },
      { path: "verify-email", element: <VerifyEmailPage /> },
      {
        path: "status",
        lazy: async () => {
          const { StatusPage } = await import("@/features/status/StatusPage");
          return { Component: StatusPage };
        },
      },
      // Public browsing — backend enforces all auth/access on every API call
      { path: "resources", element: <BrowsePage /> },
      { path: "resources/:id", element: <ResourceDetailPage /> },
      { path: "catalog", element: <CatalogPage /> },
      {
        element: <RequireAuth />,
        children: [
          // ── Shared / account ─────────────────────────────────────────────
          { path: "account", element: <AccountPage /> },
          { path: "bookmarks", element: <BookmarksPage /> },
          { path: "notifications", element: <NotificationsPage /> },
          { path: "help", element: <HelpPage /> },
          { path: "pay/fake/:id", element: <FakeCheckoutPage /> },
          { path: "payments/:id", element: <PaymentReturnPage /> },

          // ── Student dashboard ─────────────────────────────────────────────
          // /dashboard dispatches to the right role-specific dashboard.
          // For STUDENT users it renders StudentDashboard directly.
          // For other roles it redirects to their own workspace root.
          { path: "dashboard", element: <DashboardPage /> },

          // ── Student: printing ─────────────────────────────────────────────
          {
            path: "print",
            element: (
              <RequirePermission permission="order:create">
                <NewPrintOrderPage />
              </RequirePermission>
            ),
          },
          {
            path: "print/orders",
            element: (
              <RequirePermission permission="order:read">
                <PrintOrdersPage />
              </RequirePermission>
            ),
          },
          {
            path: "print/orders/:id",
            element: (
              <RequirePermission permission="order:read">
                <PrintOrderPage />
              </RequirePermission>
            ),
          },

          // ── Printing Operator workspace ───────────────────────────────────
          {
            path: "operator/dashboard",
            element: (
              <RequirePermission permission="order:read_any">
                <OperatorDashboardPage />
              </RequirePermission>
            ),
          },
          {
            path: "operator",
            element: (
              <RequirePermission permission="order:read_any">
                <OperatorQueuePage />
              </RequirePermission>
            ),
          },
          {
            path: "operator/orders/:id",
            element: (
              <RequirePermission permission="order:read_any">
                <OperatorOrderPage />
              </RequirePermission>
            ),
          },

          // ── Resource Provider workspace ───────────────────────────────────
          {
            path: "provider/dashboard",
            element: (
              <RequirePermission permission="resource:create">
                <ProviderDashboardPage />
              </RequirePermission>
            ),
          },
          {
            path: "provider/resources",
            element: (
              <RequirePermission permission="resource:create">
                <ProviderResourcesPage />
              </RequirePermission>
            ),
          },
          {
            path: "provider/resources/new",
            element: (
              <RequirePermission permission="resource:create">
                <ProviderResourceFormPage />
              </RequirePermission>
            ),
          },
          {
            path: "provider/resources/:id",
            element: (
              <RequirePermission permission="resource:create">
                <ProviderResourceFormPage />
              </RequirePermission>
            ),
          },

          // ── Moderation (shared between Admin and Resource Provider reviewer)
          {
            path: "moderation",
            element: (
              <RequirePermission permission="resource:review">
                <ModerationPage />
              </RequirePermission>
            ),
          },

          // ── Admin workspace ───────────────────────────────────────────────
          {
            path: "admin",
            element: (
              <RequirePermission permission="user:read">
                <AdminPage />
              </RequirePermission>
            ),
          },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
