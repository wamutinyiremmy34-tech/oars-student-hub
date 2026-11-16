import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, Navigate, useLocation } from "react-router-dom";
import { z } from "zod";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { TextField } from "@/components/ui/Field";
import { useAuth } from "@/features/auth/auth-context";
import { safeRedirect } from "@/features/auth/forms";
import { toUserMessage } from "@/lib/api/errors";

const loginSchema = z.object({
  email: z.email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});
type LoginValues = z.infer<typeof loginSchema>;

export function LoginPage() {
  const { state, signIn } = useAuth();
  const location = useLocation();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) });

  const destination = safeRedirect((location.state as { from?: string } | null)?.from);
  if (state.status === "authenticated") return <Navigate to={destination} replace />;

  const onSubmit = handleSubmit(async ({ email, password }) => {
    setFormError(null);
    try {
      await signIn(email, password); // on success the state flips and <Navigate> above takes over
    } catch (error) {
      setFormError(toUserMessage(error));
    }
  });

  return (
    <Card className="mx-auto max-w-md space-y-6">
      <h1 className="text-2xl font-extrabold">Sign in</h1>
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          error={errors.email?.message}
          {...register("email")}
        />
        <TextField
          label="Password"
          type="password"
          autoComplete="current-password"
          error={errors.password?.message}
          {...register("password")}
        />
        {formError && <Alert variant="error">{formError}</Alert>}
        <Button type="submit" size="lg" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <p className="text-sm text-fg-muted">
        New to OARS?{" "}
        <Link to="/register" className="font-semibold text-brand underline">
          Create an account
        </Link>
      </p>
    </Card>
  );
}
