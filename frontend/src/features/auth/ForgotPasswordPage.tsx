import { useState } from "react";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { TextField } from "@/components/ui/Field";
import { apiFetch } from "@/lib/api/client";
import { toUserMessage } from "@/lib/api/errors";
import { z } from "zod";

const msgSchema = z.object({ message: z.string() });

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setPending(true);
    setError(null);
    try {
      await apiFetch("/auth/forgot-password", {
        method: "POST",
        body: { email: email.trim() },
        schema: msgSchema,
        auth: false,
        skipAuthRefresh: true,
      });
      setDone(true);
    } catch (err) {
      setError(toUserMessage(err));
    } finally {
      setPending(false);
    }
  }

  if (done) {
    return (
      <Card className="mx-auto max-w-md space-y-4">
        <h1 className="text-2xl font-extrabold">Check your inbox</h1>
        <Alert variant="success">
          If an account exists for <strong>{email}</strong>, we've sent a password reset link. It
          expires in 1 hour.
        </Alert>
        <p className="text-sm text-fg-muted">
          Didn't receive it? Check your spam folder or{" "}
          <button
            type="button"
            className="font-semibold text-brand underline"
            onClick={() => setDone(false)}
          >
            try again
          </button>
          .
        </p>
        <Link to="/login" className="block text-sm font-semibold text-brand underline">
          Back to sign in
        </Link>
      </Card>
    );
  }

  return (
    <Card className="mx-auto max-w-md space-y-6">
      <h1 className="text-2xl font-extrabold">Reset your password</h1>
      <p className="text-fg-muted">
        Enter your account email and we'll send a reset link.
      </p>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        {error && <Alert variant="error">{error}</Alert>}
        <Button type="submit" size="lg" className="w-full" disabled={pending || !email.trim()}>
          {pending ? "Sending…" : "Send reset link"}
        </Button>
      </form>
      <p className="text-sm text-fg-muted">
        Remembered it?{" "}
        <Link to="/login" className="font-semibold text-brand underline">
          Sign in
        </Link>
      </p>
    </Card>
  );
}
