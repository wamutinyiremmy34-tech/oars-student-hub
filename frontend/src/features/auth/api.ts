import { z } from "zod";
import { apiFetch } from "@/lib/api/client";
import { tokenSchema } from "@/features/auth/session";

const userSchema = z.object({
  id: z.string(),
  email: z.string(),
  full_name: z.string(),
  phone: z.string().nullable(),
  status: z.string(),
  email_verified: z.boolean(),
  created_at: z.string(),
});

export const meSchema = z.object({
  user: userSchema,
  student_profile: z
    .object({
      institution_id: z.string(),
      program_id: z.string().nullable(),
      student_number: z.string().nullable(),
      year_of_study: z.number().nullable(),
    })
    .nullable(),
  roles: z.array(z.object({ role: z.string(), institution_id: z.string().nullable() })),
  permissions: z.array(z.object({ permission: z.string(), institution_id: z.string().nullable() })),
});
export type Me = z.infer<typeof meSchema>;

const institutionSchema = z.object({
  id: z.string(),
  name: z.string(),
  code: z.string(),
  slug: z.string(),
});
export type Institution = z.infer<typeof institutionSchema>;

const messageSchema = z.object({ message: z.string() });
const registerOutSchema = z.object({ user: userSchema });

export interface RegisterInput {
  email: string;
  password: string;
  full_name: string;
  institution_id: string;
  student_number?: string;
  phone?: string;
}

export function login(email: string, password: string) {
  return apiFetch("/auth/login", {
    method: "POST",
    body: { email, password },
    schema: tokenSchema,
    auth: false,
    skipAuthRefresh: true,
  });
}

export function registerStudent(input: RegisterInput) {
  return apiFetch("/auth/register", {
    method: "POST",
    body: input,
    schema: registerOutSchema,
    auth: false,
    skipAuthRefresh: true,
  });
}

export function logout() {
  return apiFetch("/auth/logout", {
    method: "POST",
    schema: messageSchema,
    auth: false,
    skipAuthRefresh: true,
  });
}

export function getMe(signal?: AbortSignal) {
  return apiFetch("/me", { schema: meSchema, signal });
}

export function listInstitutions(signal?: AbortSignal) {
  return apiFetch("/institutions", {
    schema: z.array(institutionSchema),
    auth: false,
    signal,
  });
}

export function updateProfile(body: { full_name?: string; phone?: string }) {
  return apiFetch("/me", { method: "PATCH", body, schema: meSchema });
}

export function forgotPassword(email: string) {
  return apiFetch("/auth/forgot-password", {
    method: "POST",
    body: { email },
    schema: messageSchema,
    auth: false,
    skipAuthRefresh: true,
  });
}

export function resetPassword(token: string, password: string) {
  return apiFetch("/auth/reset-password", {
    method: "POST",
    body: { token, new_password: password },
    schema: messageSchema,
    auth: false,
    skipAuthRefresh: true,
  });
}
