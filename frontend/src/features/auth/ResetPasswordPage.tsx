import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PasswordField } from "@/components/ui/Field";
import { apiFetch } from "@/lib/api/client";
import { toUserMessage } from "@/lib/api/errors";
import { z } from "zod";

const msgSchema = z.object({ message: z.string() });

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [pending, setPending] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  if (!token) {
    return (
      <Card className="mx-auto max-w-md space-y-4">
        <h1 className="text-2xl font-extrabold">Invalid link</h1>
        <p className="text-fg-muted">This reset link is missing its token. Please request a new one.</p>
        <Link to="/forgot-password" className="font-semibold text-brand underline">
          Request a new reset link
        </Link>
      </Card>
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLocalError(null);
    setServerError(null);

    if (password.length < 8) {
      setLocalError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setLocalError("Passwords don't match.");
      return;
    }

    setPending(true);
    try {
      await apiFetch("/auth/reset-password", {
        method: "POST",
        body: { token, new_password: password },
        schema: msgSchema,
        auth: false,
        skipAuthRefresh: true,
      });
      navigate("/login", { state: { flash: "Password updated. Please sign in." } });
    } catch (err) {
      setServerError(toUserMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <Card className="mx-auto max-w-md space-y-6">
      <h1 className="text-2xl font-extrabold">Set a new password</h1>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <PasswordField
          label="New password"
          autoComplete="new-password"
          hint="At least 8 characters"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <PasswordField
          label="Confirm new password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          required
        />
        {(localError ?? serverError) && (
          <Alert variant="error">{localError ?? serverError}</Alert>
        )}
        <Button type="submit" size="lg" className="w-full" disabled={pending}>
          {pending ? "Saving…" : "Set password"}
        </Button>
      </form>
      <p className="text-sm text-fg-muted">
        <Link to="/login" className="font-semibold text-brand underline">
          Back to sign in
        </Link>
      </p>
    </Card>
  );
}
