import { Navigate, Link } from "react-router-dom";
import { buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { BookOpen, Printer, Bell, GraduationCap, ArrowRight } from "@/components/ui/Icon";
import { useAuth } from "@/features/auth/auth-context";

export function HomePage() {
  const { state } = useAuth();

  if (state.status === "authenticated") {
    return <Navigate to="/dashboard" replace />;
  }

  if (state.status === "loading") {
    return (
      <div className="flex justify-center py-16" role="status">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand border-t-transparent" aria-label="Loading" />
      </div>
    );
  }

  return (
    <div className="space-y-10">
      {/* Hero */}
      <section className="rounded-card bg-gradient-to-br from-primary to-primary-hover px-6 py-10 sm:px-10 sm:py-14 text-white space-y-5">
        <div className="space-y-3 max-w-xl">
          <h1 className="text-3xl sm:text-4xl font-extrabold leading-tight tracking-tight">
            OARS Student Solutions
          </h1>
          <p className="text-base sm:text-lg opacity-90 leading-relaxed">
            Find lecture notes, past papers and study resources from Ugandan universities.
            Print documents at your campus shop and track your orders in real time.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link
            to="/register"
            className={buttonClasses({
              variant: "primary",
              size: "lg",
              className: "bg-white text-primary hover:bg-white/90 font-bold",
            })}
          >
            Get started — it's free
          </Link>
          <Link
            to="/login"
            className={buttonClasses({
              variant: "ghost",
              size: "lg",
              className: "text-white hover:bg-white/10 border border-white/30",
            })}
          >
            Sign in
          </Link>
          <Link
            to="/resources"
            className={buttonClasses({
              variant: "ghost",
              size: "lg",
              className: "text-white hover:bg-white/10",
            })}
          >
            Browse resources
          </Link>
        </div>
      </section>

      {/* Feature cards */}
      <section aria-label="Features">
        <h2 className="sr-only">What OARS offers</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <FeatureCard
            icon={<BookOpen size="lg" className="text-secondary" />}
            title="Academic resources"
            body="Lecture notes, past papers, textbooks and more — curated for Makerere, Kyambogo, MUST, UCU and IUIU."
            to="/resources"
            linkLabel="Browse resources"
          />
          <FeatureCard
            icon={<GraduationCap size="lg" className="text-accent" />}
            title="Browse by course"
            body="Navigate by faculty and programme to find exactly the resources for your subjects."
            to="/catalog"
            linkLabel="Browse courses"
          />
          <FeatureCard
            icon={<Printer size="lg" className="text-warning" />}
            title="Campus printing"
            body="Upload your documents, choose a campus print shop, and track your order from submission to pickup."
            to="/register"
            linkLabel="Start printing"
          />
          <FeatureCard
            icon={<Bell size="lg" className="text-primary" />}
            title="Stay informed"
            body="Get notified when your print order is ready, when new resources are published, and more."
            to="/register"
            linkLabel="Create account"
          />
        </div>
      </section>

      {/* Institutions */}
      <section className="space-y-4">
        <h2 className="text-lg font-bold text-fg-muted">Supported universities</h2>
        <div className="flex flex-wrap gap-2">
          {["Makerere University", "Kyambogo University", "MUST", "UCU", "IUIU"].map((u) => (
            <span
              key={u}
              className="rounded-full border border-line bg-raised px-4 py-2 text-sm font-medium text-fg-muted"
            >
              {u}
            </span>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="rounded-card border border-brand/20 bg-brand/5 p-6 space-y-4">
        <h2 className="text-xl font-bold">Ready to get started?</h2>
        <p className="text-fg-muted">
          Create a free account today and access hundreds of academic resources from your university.
        </p>
        <Link
          to="/register"
          className={buttonClasses({ variant: "primary", size: "lg" })}
        >
          Create free account
          <ArrowRight size="sm" aria-hidden />
        </Link>
      </section>
    </div>
  );
}

function FeatureCard({
  icon,
  title,
  body,
  to,
  linkLabel,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
  to: string;
  linkLabel: string;
}) {
  return (
    <Card className="flex flex-col gap-3 hover:shadow-lifted transition-shadow">
      <div className="p-2 rounded-control bg-surface w-fit">{icon}</div>
      <h3 className="font-bold text-base">{title}</h3>
      <p className="text-sm text-fg-muted flex-1 leading-relaxed">{body}</p>
      <Link
        to={to}
        className="text-sm font-semibold text-secondary hover:underline inline-flex items-center gap-1 mt-auto"
      >
        {linkLabel}
        <ArrowRight size="xs" aria-hidden />
      </Link>
    </Card>
  );
}
