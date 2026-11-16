import { Link } from "react-router-dom";
import { buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

export function NotFoundPage() {
  return (
    <Card className="space-y-4">
      <h1 className="text-2xl font-extrabold">Page not found</h1>
      <p className="text-fg-muted">The page you're looking for doesn't exist or has moved.</p>
      <Link to="/" className={buttonClasses({ variant: "secondary" })}>
        Back to home
      </Link>
    </Card>
  );
}
