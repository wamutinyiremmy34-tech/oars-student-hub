import { Link, useNavigate } from "react-router-dom";
import { buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Search, ArrowRight } from "@/components/ui/Icon";

export function NotFoundPage() {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col items-center gap-8 py-16 text-center">
      {/* Visual treatment */}
      <div className="relative">
        <div className="text-[8rem] font-extrabold leading-none text-brand/10 select-none">
          404
        </div>
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="rounded-full bg-raised border border-line p-5 shadow-lifted">
            <Search size="xl" className="text-fg-muted" aria-hidden />
          </div>
        </div>
      </div>

      {/* Message */}
      <div className="space-y-2 max-w-md">
        <h1 className="text-2xl font-extrabold">Page not found</h1>
        <p className="text-fg-muted">
          The page you're looking for doesn't exist or has moved. Check the URL or navigate back.
        </p>
      </div>

      {/* Actions */}
      <div className="flex flex-wrap gap-3 justify-center">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className={buttonClasses({ variant: "secondary" })}
        >
          Go back
        </button>
        <Link to="/" className={buttonClasses({ variant: "primary" })}>
          Home
          <ArrowRight size="sm" aria-hidden />
        </Link>
        <Link to="/resources" className={buttonClasses({ variant: "ghost" })}>
          Browse resources
        </Link>
      </div>

      {/* Quick links */}
      <Card className="w-full max-w-sm space-y-2 text-left" variant="flat">
        <p className="text-sm font-semibold text-fg-muted">Quick links</p>
        <div className="space-y-1">
          {[
            { to: "/dashboard",   label: "Dashboard" },
            { to: "/resources",   label: "Find resources" },
            { to: "/catalog",     label: "Browse courses" },
            { to: "/print",       label: "New print order" },
            { to: "/help",        label: "Help & support" },
          ].map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className="flex items-center justify-between gap-2 rounded-control px-3 py-2 text-sm hover:bg-surface transition-colors group"
            >
              <span>{item.label}</span>
              <ArrowRight size="xs" className="text-fg-muted group-hover:text-brand" aria-hidden />
            </Link>
          ))}
        </div>
      </Card>
    </div>
  );
}
