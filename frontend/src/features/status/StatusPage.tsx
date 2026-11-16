import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { getReadiness } from "@/features/status/api";
import { toUserMessage } from "@/lib/api/errors";

export function StatusPage() {
  const query = useQuery({
    queryKey: ["system", "ready"],
    queryFn: ({ signal }) => getReadiness(signal),
    retry: false,
  });

  return (
    <Card>
      <h1 className="text-2xl font-extrabold">System status</h1>

      {query.isPending && (
        <p role="status" className="mt-4 text-fg-muted">
          Checking…
        </p>
      )}

      {query.isError && (
        <div className="mt-4 space-y-4">
          <p role="alert" className="font-semibold text-danger-strong dark:text-danger">
            {toUserMessage(query.error)}
          </p>
          <Button onClick={() => void query.refetch()} disabled={query.isFetching}>
            Try again
          </Button>
        </div>
      )}

      {query.isSuccess && (
        <div className="mt-4 space-y-2">
          <p className="font-semibold">All systems ready.</p>
          <ul className="text-fg-muted">
            {Object.entries(query.data.checks).map(([name, state]) => (
              <li key={name}>
                {name}: {state}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
