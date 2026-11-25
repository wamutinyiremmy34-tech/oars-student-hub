import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Card } from "@/components/ui/Card";
import { buttonClasses } from "@/components/ui/Button";
import { apiFetch } from "@/lib/api/client";
import { toUserMessage } from "@/lib/api/errors";
import { z } from "zod";

const msgSchema = z.object({ message: z.string() });

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [status, setStatus] = useState<"pending" | "success" | "error">("pending");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("No verification token found in this link.");
      return;
    }
    apiFetch("/auth/verify", {
      method: "POST",
      body: { token },
      schema: msgSchema,
      auth: false,
      skipAuthRefresh: true,
    })
      .then(() => setStatus("success"))
      .catch((err) => {
        setStatus("error");
        setMessage(toUserMessage(err));
      });
  }, [token]);

  return (
    <Card className="mx-auto max-w-md space-y-4">
      <h1 className="text-2xl font-extrabold">Email verification</h1>
      {status === "pending" && <p role="status" className="text-fg-muted">Verifying…</p>}
      {status === "success" && (
        <>
          <Alert variant="success">Your email has been verified. You're all set!</Alert>
          <Link to="/dashboard" className={buttonClasses({ size: "lg", className: "w-full" })}>
            Go to dashboard
          </Link>
        </>
      )}
      {status === "error" && (
        <>
          <Alert variant="error">{message || "Verification failed. This link may have expired."}</Alert>
          <p className="text-sm text-fg-muted">
            <Link to="/login" className="font-semibold text-brand underline">
              Sign in
            </Link>{" "}
            or{" "}
            <Link to="/register" className="font-semibold text-brand underline">
              create a new account
            </Link>
            .
          </p>
        </>
      )}
    </Card>
  );
}
