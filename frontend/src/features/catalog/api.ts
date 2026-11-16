import { z } from "zod";
import { apiFetch, apiFetchPage } from "@/lib/api/client";
import { toQueryString } from "@/features/resources/api";

const faculty = z.object({ id: z.string(), institution_id: z.string(), name: z.string(), kind: z.string(), code: z.string().nullable() });
const program = z.object({ id: z.string(), institution_id: z.string(), faculty_id: z.string(), name: z.string(), level: z.string(), code: z.string().nullable() });
const course = z.object({ id: z.string(), institution_id: z.string(), faculty_id: z.string(), code: z.string(), title: z.string() });
export type Faculty = z.infer<typeof faculty>;
export type Program = z.infer<typeof program>;
export type Course = z.infer<typeof course>;

export const listFaculties = (institutionId: string, signal?: AbortSignal) =>
  apiFetch(`/faculties${toQueryString({ institution_id: institutionId })}`, { schema: z.array(faculty), auth: false, signal });

export const listPrograms = (institutionId: string, facultyId?: string, signal?: AbortSignal) =>
  apiFetch(`/programs${toQueryString({ institution_id: institutionId, faculty_id: facultyId })}`, { schema: z.array(program), auth: false, signal });

export const listCourses = (
  params: { institution_id: string; faculty_id?: string; program_id?: string; q?: string; page?: number; page_size?: number },
  signal?: AbortSignal,
) => apiFetchPage(`/courses${toQueryString({ ...params })}`, { schema: z.array(course), auth: false, signal });
