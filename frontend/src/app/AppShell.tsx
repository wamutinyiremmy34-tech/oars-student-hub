import { useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { OfflineBanner } from "@/components/OfflineBanner";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Menu, X } from "@/components/ui/Icon";
import { useAuth } from "@/features/auth/auth-context";
import { useRole } from "@/features/auth/use-role";
import { NotificationBell } from "@/features/notifications/NotificationBell";
import {
  ADMIN_NAV,
  OPERATOR_NAV,
  PROVIDER_NAV,
  STUDENT_NAV,
  type NavItem,
} from "@/app/nav-config";
import { cn } from "@/lib/cn";

// ─── Role badge ───────────────────────────────────────────────────────────────

function RoleBadge({ role }: { role: string }) {
  const labels: Record<string, string> = {
    ADMIN: "Admin",
    RESOURCE_PROVIDER: "Provider",
    PRINTING_OPERATOR: "Operator",
    STUDENT: "Student",
  };
  const colors: Record<string, string> = {
    ADMIN: "bg-danger/10 text-danger-strong border border-danger/20",
    RESOURCE_PROVIDER: "bg-secondary/10 text-secondary border border-secondary/20",
    PRINTING_OPERATOR: "bg-warning/10 text-warning border border-warning/20",
    STUDENT: "bg-brand/10 text-brand border border-brand/20",
  };
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-xs font-bold tracking-wide",
        colors[role] ?? "bg-surface text-fg-muted",
      )}
    >
      {labels[role] ?? role}
    </span>
  );
}

// ─── Single nav link ──────────────────────────────────────────────────────────

function NavLink({ to, children }: { to: string; children: React.ReactNode }) {
  const { pathname } = useLocation();
  const active =
    pathname === to ||
    (to !== "/" && to.length > 1 && pathname.startsWith(to + "/")) ||
    (to !== "/" && to.length > 1 && pathname === to);

  return (
    <Link
      to={to}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-control px-3 py-2 text-sm font-medium transition-colors",
        "hover:bg-surface hover:text-fg",
        active
          ? "bg-brand/10 font-semibold text-brand"
          : "text-fg-muted",
      )}
    >
      {children}
    </Link>
  );
}

// ─── Whether the current role gets a wider layout ────────────────────────────

function useWideLayout(role: string | null): boolean {
  return role === "ADMIN";
}

// ─── AppShell ─────────────────────────────────────────────────────────────────

export function AppShell() {
  const { state, signOut } = useAuth();
  const role = useRole();
  const [menuOpen, setMenuOpen] = useState(false);
  const wide = useWideLayout(role);

  const isAuth    = state.status === "authenticated";
  const isLoading = state.status === "loading";

  let navItems: NavItem[] = [];
  if (isAuth) {
    switch (role) {
      case "ADMIN":            navItems = ADMIN_NAV;    break;
      case "RESOURCE_PROVIDER":navItems = PROVIDER_NAV; break;
      case "PRINTING_OPERATOR":navItems = OPERATOR_NAV; break;
      default:                 navItems = STUDENT_NAV;
    }
  }

  const primaryLinks = (
    <>
      {!isAuth && (
        <>
          <NavLink to="/resources">Resources</NavLink>
          <NavLink to="/catalog">Courses</NavLink>
        </>
      )}
      {navItems.map((item) => (
        <NavLink key={item.to} to={item.to}>
          {item.label}
        </NavLink>
      ))}
    </>
  );

  const contentMaxWidth = wide ? "max-w-screen-2xl" : "max-w-5xl";

  return (
    <div className="flex min-h-dvh flex-col">
      {/* Skip to content */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-control focus:bg-raised focus:px-4 focus:py-2 focus:shadow-lifted focus:text-fg"
      >
        Skip to content
      </a>

      <OfflineBanner />

      {/* ── Header ────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 border-b border-line bg-raised/95 backdrop-blur-sm">
        <div className={cn("mx-auto flex min-h-16 items-center justify-between gap-2 px-4 py-2", contentMaxWidth)}>

          {/* Logo */}
          <Link
            to="/"
            aria-label="OARS Student Solutions — home"
            className="shrink-0 font-extrabold text-brand tracking-tight text-xl hover:opacity-80 transition-opacity"
          >
            OARS
          </Link>

          {/* Desktop nav */}
          <nav aria-label="Primary navigation" className="hidden lg:flex flex-wrap items-center gap-0.5 flex-1 px-4">
            {primaryLinks}
          </nav>

          {/* Right side */}
          <div className="flex items-center gap-1.5 shrink-0">
            {isAuth ? (
              <>
                <NotificationBell />

                {/* Role badge + name — hidden on tiny screens */}
                <div className="hidden sm:flex items-center gap-1.5">
                  {role && <RoleBadge role={role} />}
                  <Link
                    to="/account"
                    className={cn(
                      buttonClasses({ variant: "ghost" }),
                      "text-sm max-w-[120px] truncate",
                    )}
                  >
                    {state.me.user.full_name.split(" ")[0]}
                  </Link>
                </div>

                {/* Mobile account icon */}
                <Link
                  to="/account"
                  aria-label="Account"
                  className={cn(
                    "sm:hidden inline-flex min-h-10 min-w-10 items-center justify-center rounded-control hover:bg-surface transition-colors",
                  )}
                >
                  <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="8" r="4" />
                    <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
                  </svg>
                </Link>

                <Button
                  variant="secondary"
                  size="md"
                  onClick={() => void signOut()}
                  className="hidden sm:inline-flex"
                >
                  Sign out
                </Button>
              </>
            ) : !isLoading ? (
              <>
                <Link to="/login" className={cn(buttonClasses({ variant: "ghost" }), "hidden sm:inline-flex")}>
                  Sign in
                </Link>
                <Link to="/register" className={buttonClasses({ variant: "primary" })}>
                  Register
                </Link>
              </>
            ) : null}

            <ThemeToggle />

            {/* Hamburger */}
            <button
              type="button"
              aria-label={menuOpen ? "Close menu" : "Open navigation menu"}
              aria-expanded={menuOpen}
              aria-controls="mobile-nav"
              onClick={() => setMenuOpen((v) => !v)}
              className="lg:hidden inline-flex min-h-10 min-w-10 items-center justify-center rounded-control hover:bg-surface transition-colors"
            >
              {menuOpen ? <X size="md" /> : <Menu size="md" />}
            </button>
          </div>
        </div>

        {/* Mobile nav panel */}
        {menuOpen && (
          <nav
            id="mobile-nav"
            aria-label="Mobile navigation"
            className="border-t border-line bg-raised px-4 py-3 lg:hidden"
          >
            <div
              className="flex flex-col gap-0.5"
              onClick={() => setMenuOpen(false)}
            >
              {primaryLinks}

              {/* Auth actions in mobile menu */}
              {isAuth && (
                <div className="mt-2 pt-2 border-t border-line flex flex-col gap-1">
                  {role && (
                    <p className="px-3 py-1 text-xs text-fg-muted font-semibold uppercase tracking-widest">
                      {role.replace("_", " ")}
                    </p>
                  )}
                  <NavLink to="/account">Account</NavLink>
                  <button
                    type="button"
                    onClick={() => void signOut()}
                    className="text-left rounded-control px-3 py-2 text-sm font-medium text-fg-muted hover:bg-surface hover:text-fg transition-colors"
                  >
                    Sign out
                  </button>
                </div>
              )}
              {!isAuth && !isLoading && (
                <div className="mt-2 pt-2 border-t border-line">
                  <NavLink to="/login">Sign in</NavLink>
                </div>
              )}
            </div>
          </nav>
        )}
      </header>

      {/* ── Main content ──────────────────────────────────────────────────── */}
      <main
        id="main"
        className={cn(
          "mx-auto w-full flex-1 px-4 py-6 sm:py-8",
          contentMaxWidth,
        )}
      >
        <Outlet />
      </main>

      {/* ── Footer ────────────────────────────────────────────────────────── */}
      <footer className="border-t border-line bg-raised px-4 py-4 text-center text-xs text-fg-muted">
        © {new Date().getFullYear()} OARS Technologies ·{" "}
        <span className="hidden sm:inline">Academic resources for Ugandan universities · </span>
        <Link to="/status" className="hover:underline">System status</Link>
      </footer>
    </div>
  );
}
