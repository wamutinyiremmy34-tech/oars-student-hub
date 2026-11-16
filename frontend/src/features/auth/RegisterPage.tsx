import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";
import { Alert } from "@/components/ui/Alert";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SelectField, TextField } from "@/components/ui/Field";
import { listInstitutions, registerStudent } from "@/features/auth/api";
import { applyServerFieldErrors } from "@/features/auth/forms";
import { ApiError, toUserMessage } from "@/lib/api/errors";

const registerSchema = z
  .object({
    full_name: z.string().trim().min(1, "Enter your full name").max(120, "That name is too long"),
    email: z.email("Enter a valid email address"),
    institution_id: z.string().min(1, "Choose your university"),
    student_number: z.string().trim().max(50, "That number is too long").optional(),
    phone: z
      .string()
      .trim()
      .regex(/^(\+?[0-9]{9,15})?$/, "Enter a valid phone number, for example +256700123456")
      .optional(),
    password: z.string().min(10, "Use at least 10 characters").max(128, "That password is too long"),
    confirm_password: z.string().min(1, "Repeat your password"),
  })
  .refine((values) => values.password === values.confirm_password, {
    path: ["confirm_password"],
    message: "Passwords do not match",
  });
type RegisterValues = z.infer<typeof registerSchema>;

const SERVER_FIELDS = ["email", "password", "full_name", "institution_id", "student_number", "phone"];

export function RegisterPage() {
  const [formError, setFormError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const institutions = useQuery({
    queryKey: ["institutions"],
    queryFn: ({ signal }) => listInstitutions(signal),
    staleTime: 5 * 60_000,
  });
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await registerStudent({
        email: values.email,
        password: values.password,
        full_name: values.full_name,
        institution_id: values.institution_id,
        student_number: values.student_number || undefined,
        phone: values.phone || undefined,
      });
      setDone(true);
    } catch (error) {
      if (error instanceof ApiError && error.code === "email_taken") {
        setError("email", { type: "server", message: "An account with this email already exists." });
      } else if (error instanceof ApiError && error.code === "student_number_taken") {
        setError("student_number", { type: "server", message: error.message });
      } else if (!applyServerFieldErrors(error, setError, SERVER_FIELDS)) {
        setFormError(toUserMessage(error));
      }
    }
  });

  if (done) {
    return (
      <Card className="mx-auto max-w-md space-y-4">
        <h1 className="text-2xl font-extrabold">Account created</h1>
        <Alert variant="success">
          We sent a verification link to your email. You can sign in now and verify later.
        </Alert>
        <Link to="/login" className={buttonClasses({ size: "lg", className: "w-full" })}>
          Go to sign in
        </Link>
      </Card>
    );
  }

  return (
    <Card className="mx-auto max-w-md space-y-6">
      <h1 className="text-2xl font-extrabold">Create your account</h1>
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <TextField
          label="Full name"
          autoComplete="name"
          error={errors.full_name?.message}
          {...register("full_name")}
        />
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          error={errors.email?.message}
          {...register("email")}
        />
        <SelectField
          label="University"
          defaultValue=""
          error={errors.institution_id?.message}
          hint={institutions.isError ? undefined : "Choose the university you attend."}
          disabled={institutions.isPending}
          {...register("institution_id")}
        >
          <option value="" disabled>
            {institutions.isPending ? "Loading universities…" : "Select your university"}
          </option>
          {institutions.data?.map((institution) => (
            <option key={institution.id} value={institution.id}>
              {institution.name}
            </option>
          ))}
        </SelectField>
        {institutions.isError && (
          <Alert variant="error">
            {toUserMessage(institutions.error)}{" "}
            <button type="button" className="underline" onClick={() => void institutions.refetch()}>
              Try again
            </button>
          </Alert>
        )}
        <TextField
          label="Student number (optional)"
          autoComplete="off"
          error={errors.student_number?.message}
          {...register("student_number")}
        />
        <TextField
          label="Phone (optional)"
          type="tel"
          autoComplete="tel"
          error={errors.phone?.message}
          {...register("phone")}
        />
        <TextField
          label="Password"
          type="password"
          autoComplete="new-password"
          hint="At least 10 characters."
          error={errors.password?.message}
          {...register("password")}
        />
        <TextField
          label="Repeat password"
          type="password"
          autoComplete="new-password"
          error={errors.confirm_password?.message}
          {...register("confirm_password")}
        />
        {formError && <Alert variant="error">{formError}</Alert>}
        <Button type="submit" size="lg" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? "Creating account…" : "Create account"}
        </Button>
      </form>
      <p className="text-sm text-fg-muted">
        Already have an account?{" "}
        <Link to="/login" className="font-semibold text-brand underline">
          Sign in
        </Link>
      </p>
    </Card>
  );
}
