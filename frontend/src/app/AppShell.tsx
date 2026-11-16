import { useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { OfflineBanner } from "@/components/OfflineBanner";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button, buttonClasses } from "@/components/ui/Button";
import { useAuth } from "@/features/auth/auth-context";
import { NotificationBell } from "@/features/notifications/NotificationBell";
import { cn } from "@/lib/cn";

function NavLink({ to, children }: { to: string; children: React.ReactNode }) {
  const { pathname } = useLocation();
  const active = pathname === to || (to !== "/" && pathname.startsWith(to));
  return (
    <Link
      to={to}
      className={cn(
        buttonClasses({ variant: "ghost" }),
        active && "bg-surface font-bold text-brand",
      )}
    >
      {children}
    </Link>
  );
}

export function AppShell() {
  const { state, signOut, can } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  const isAuth = state.status === "authenticated";
  const isLoading = state.status === "loading";

  const primaryLinks = (
    <>
      <NavLink to="/resources">Resources</NavLink>
      <NavLink to="/catalog">Courses</NavLink>
      {isAuth && (
        <>
          <NavLink to="/dashboard">Dashboard</NavLink>
          <NavLink to="/bookmarks">Saved</NavLink>
          {can("order:create") && <NavLink to="/print">Print</NavLink>}
          {can("order:read") && <NavLink to="/print/orders">My orders</NavLink>}
          {can("order:read_any") && <NavLink to="/operator">Print queue</NavLink>}
          {can("resource:create") && <NavLink to="/provider/resources">My resources</NavLink>}
          {can("resource:review") && <NavLink to="/moderation">Moderation</NavLink>}
          {(can("user:read") || can("advertisement:manage") || can("analytics:read")) && (
            <NavLink to="/admin">Admin</NavLink>
          )}
        </>
      )}
    </>
  );

  return (
    <div className="flex min-h-dvh flex-col">
      {/* Skip link for keyboard / screen-reader users */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-control focus:bg-raised focus:px-4 focus:py-2"
      >
        Skip to content
      </a>

      <OfflineBanner />

      <header className="sticky top-0 z-40 border-b border-line bg-raised/95 backdrop-blur-sm">
        <div className="mx-auto flex min-h-16 max-w-5xl items-center justify-between gap-2 px-4 py-2">
          {/* Logo */}
          <Link to="/" className="text-xl font-extrabold text-brand shrink-0">
            OARS
          </Link>

          {/* Desktop nav */}
          <nav aria-label="Primary" className="hidden md:flex flex-wrap items-center gap-1">
            {primaryLinks}
          </nav>

          {/* Right side controls */}
          <div className="flex items-center gap-1">
            {isAuth ? (
              <>
                <NotificationBell />
                <Link to="/account" className={buttonClasses({ variant: "ghost" })}>
                  <span className="hidden sm:inline">{state.me.user.full_name.split(" ")[0]}</span>
                  <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="sm:hidden">
                    <circle cx="12" cy="8" r="4" /><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
                  </svg>
                </Link>
                <Button variant="secondary" size="md" onClick={() => void signOut()}>
                  Sign out
                </Button>
              </>
            ) : !isLoading ? (
              <>
                <Link to="/login" className={buttonClasses({ variant: "ghost" })}>Sign in</Link>
                <Link to="/register" className={buttonClasses({ variant: "primary" })}>Register</Link>
              </>
            ) : null}

            <ThemeToggle />

            {/* Hamburger (mobile) */}
            <button
              type="button"
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              aria-expanded={menuOpen}
              aria-controls="mobile-nav"
              onClick={() => setMenuOpen((v) => !v)}
              className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-control hover:bg-surface md:hidden"
            >
              {menuOpen ? (
                <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              ) : (
                <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="18" x2="21" y2="18" />
                </svg>
              )}
            </button>
          </div>
        </div>

        {/* Mobile nav panel */}
        {menuOpen && (
          <nav
            id="mobile-nav"
            aria-label="Mobile navigation"
            className="border-t border-line bg-raised px-4 py-3 md:hidden"
          >
            <div className="flex flex-col gap-1" onClick={() => setMenuOpen(false)}>
              {primaryLinks}
            </div>
          </nav>
        )}
      </header>

      <main id="main" className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:py-8">
        <Outlet />
      </main>

      <footer className="border-t border-line bg-raised px-4 py-4 text-center text-xs text-fg-muted">
        © {new Date().getFullYear()} OARS Technologies · Academic resources for Ugandan universities
      </footer>
    </div>
  );
}
