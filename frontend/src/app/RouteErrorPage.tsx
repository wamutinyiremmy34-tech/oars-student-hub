import { useEffect } from "react";
import { useRouteError } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

export function RouteErrorPage() {
  const error = useRouteError();

  useEffect(() => {
    // Details go to the console/monitoring, never to the user.
    console.error("Route error:", error);
  }, [error]);

  return (
    <div className="mx-auto max-w-xl p-4">
      <Card className="space-y-4">
        <h1 className="text-2xl font-extrabold">Something went wrong</h1>
        <p className="text-fg-muted">An unexpected error occurred. Please reload the page.</p>
        <Button onClick={() => window.location.reload()}>Reload</Button>
      </Card>
    </div>
  );
}
