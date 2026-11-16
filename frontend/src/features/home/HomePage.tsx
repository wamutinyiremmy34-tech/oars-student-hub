import { Navigate } from "react-router-dom";
import { Link } from "react-router-dom";
import { buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useAuth } from "@/features/auth/auth-context";

export function HomePage() {
  const { state } = useAuth();

  // Authenticated users land on their dashboard.
  if (state.status === "authenticated") {
    return <Navigate to="/dashboard" replace />;
  }

  // Public landing page for unauthenticated visitors.
  if (state.status === "loading") {
    return <p role="status" className="text-fg-muted text-center py-12">Loading…</p>;
  }

  return (
    <div className="space-y-8">
      <Card className="space-y-5">
        <div className="space-y-2">
          <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">OARS Student Solutions</h1>
          <p className="text-fg-muted text-lg">
            Notes, past papers and study materials from Ugandan universities, in one place.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link to="/register" className={buttonClasses({ variant: "primary", size: "lg" })}>
            Get started — it's free
          </Link>
          <Link to="/login" className={buttonClasses({ variant: "secondary", size: "lg" })}>
            Sign in
          </Link>
          <Link to="/resources" className={buttonClasses({ variant: "ghost", size: "lg" })}>
            Browse resources
          </Link>
        </div>
      </Card>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card className="space-y-2">
          <h2 className="font-bold">📚 Academic resources</h2>
          <p className="text-sm text-fg-muted">
            Lecture notes, past papers, textbooks and more — curated for Makerere, Kyambogo, MUST, UCU and IUIU.
          </p>
          <Link to="/resources" className="text-sm text-secondary hover:underline">
            Browse resources →
          </Link>
        </Card>
        <Card className="space-y-2">
          <h2 className="font-bold">🖨️ Campus printing</h2>
          <p className="text-sm text-fg-muted">
            Upload your documents, choose a campus print shop, and track your order from submission to pickup.
          </p>
          <Link to="/catalog" className="text-sm text-secondary hover:underline">
            Browse courses →
          </Link>
        </Card>
        <Card className="space-y-2">
          <h2 className="font-bold">🔔 Stay informed</h2>
          <p className="text-sm text-fg-muted">
            Get notified when your print order is ready, when new resources are published, and more.
          </p>
          <Link to="/status" className="text-sm text-secondary hover:underline">
            System status →
          </Link>
        </Card>
      </div>
    </div>
  );
}
