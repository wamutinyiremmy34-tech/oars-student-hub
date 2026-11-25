/**
 * AcademicManagementPanel — Full CRUD for Faculties, Programs, and Courses.
 * Hierarchy: Institution → Faculty → Program / Course
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { TextField, SelectField } from "@/components/ui/Field";
import { Pagination } from "@/components/ui/Pagination";
import { listInstitutions as listAuthInstitutions } from "@/features/auth/api";
import { listFaculties, listPrograms, listCourses } from "@/features/catalog/api";
import {
  createFaculty,
  updateFaculty,
  createProgram,
  updateProgram,
  createCourse,
  updateCourse,
} from "@/features/admin/api";
import type { Faculty, Program, CourseRow } from "@/features/admin/api";
import { toUserMessage } from "@/lib/api/errors";

// ─── Faculty management ───────────────────────────────────────────────────────

function FacultySection({ institutionId }: { institutionId: string }) {
  const qc = useQueryClient();
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", kind: "FACULTY", code: "" });

  const q = useQuery({
    queryKey: ["catalog", "faculties", institutionId],
    queryFn: ({ signal }) => listFaculties(institutionId, signal),
    enabled: !!institutionId,
  });

  const create = useMutation({
    mutationFn: () => createFaculty({ institution_id: institutionId, name: form.name, kind: form.kind, code: form.code || null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["catalog", "faculties", institutionId] }); setForm({ name: "", kind: "FACULTY", code: "" }); },
  });

  const update = useMutation({
    mutationFn: () => updateFaculty(editId!, { name: form.name, kind: form.kind, code: form.code || null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["catalog", "faculties", institutionId] }); setEditId(null); },
  });

  const toggleActive = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      updateFaculty(id, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["catalog", "faculties", institutionId] }),
  });

  function startEdit(f: Faculty) {
    setEditId(f.id);
    setForm({ name: f.name, kind: f.kind, code: f.code ?? "" });
  }

  return (
    <div className="space-y-4">
      <Card className="space-y-3">
        <h3 className="font-bold text-sm">{editId ? "Edit faculty / school / college" : "Add faculty / school / college"}</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          <TextField label="Name" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} required />
          <SelectField label="Kind" value={form.kind} onChange={(e) => setForm((f) => ({ ...f, kind: e.target.value }))}>
            {["FACULTY", "SCHOOL", "COLLEGE", "INSTITUTE"].map((k) => <option key={k} value={k}>{k}</option>)}
          </SelectField>
          <TextField label="Code (optional)" value={form.code} onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))} hint="e.g. FCE" />
        </div>
        {(create.isError || update.isError) && <Alert variant="error">{toUserMessage(create.error ?? update.error)}</Alert>}
        <div className="flex gap-2">
          <Button
            size="md"
            disabled={!form.name.trim() || create.isPending || update.isPending}
            onClick={() => editId ? update.mutate() : create.mutate()}
          >
            {editId ? "Save" : "Add"}
          </Button>
          {editId && <Button size="md" variant="ghost" onClick={() => setEditId(null)}>Cancel</Button>}
        </div>
      </Card>

      {q.isPending && <p className="text-sm text-fg-muted">Loading…</p>}
      {q.isError && <Alert variant="error">{toUserMessage(q.error)}</Alert>}
      {q.data && (
        <div className="overflow-x-auto rounded-card border border-line">
          <table className="min-w-full text-sm">
            <thead className="bg-surface">
              <tr>{["Name", "Kind", "Code", "Active", "Actions"].map((h) => <th key={h} className="px-3 py-2 text-left font-semibold text-fg-muted">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-line">
              {q.data.length === 0 && <tr><td colSpan={5} className="px-3 py-4 text-center text-fg-muted">No faculties yet.</td></tr>}
              {q.data.map((f) => (
                <tr key={f.id} className={f.is_active ? "" : "opacity-60"}>
                  <td className="px-3 py-2 font-semibold">{f.name}</td>
                  <td className="px-3 py-2 text-fg-muted">{f.kind}</td>
                  <td className="px-3 py-2 font-mono">{f.code ?? "—"}</td>
                  <td className="px-3 py-2">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${f.is_active ? "bg-accent/10 text-accent" : "bg-surface text-fg-muted border border-line"}`}>
                      {f.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex gap-1">
                      <Button size="md" variant="ghost" onClick={() => startEdit(f)}>Edit</Button>
                      <button
                        onClick={() => toggleActive.mutate({ id: f.id, is_active: !f.is_active })}
                        className="text-xs text-secondary hover:underline px-2"
                      >
                        {f.is_active ? "Deactivate" : "Activate"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Program management ───────────────────────────────────────────────────────

function ProgramSection({ institutionId, faculties }: { institutionId: string; faculties: Faculty[] }) {
  const qc = useQueryClient();
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState({ faculty_id: "", name: "", code: "", level: "BACHELORS", duration_years: "" });

  const q = useQuery({
    queryKey: ["catalog", "programs", institutionId],
    queryFn: ({ signal }) => listPrograms(institutionId, undefined, signal),
    enabled: !!institutionId,
  });

  const create = useMutation({
    mutationFn: () => createProgram({
      faculty_id: form.faculty_id,
      name: form.name,
      code: form.code || null,
      level: form.level,
      duration_years: form.duration_years ? parseInt(form.duration_years, 10) : null,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["catalog", "programs", institutionId] }); setForm((f) => ({ ...f, name: "", code: "" })); },
  });

  const update = useMutation({
    mutationFn: () => updateProgram(editId!, {
      name: form.name, code: form.code || null, level: form.level,
      duration_years: form.duration_years ? parseInt(form.duration_years, 10) : null,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["catalog", "programs", institutionId] }); setEditId(null); },
  });

  const toggleActive = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) => updateProgram(id, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["catalog", "programs", institutionId] }),
  });

  function startEdit(p: Program) {
    setEditId(p.id);
    setForm({ faculty_id: p.faculty_id, name: p.name, code: p.code ?? "", level: p.level, duration_years: p.duration_years?.toString() ?? "" });
  }

  const facultyName = (id: string) => faculties.find((f) => f.id === id)?.name ?? "—";

  return (
    <div className="space-y-4">
      <Card className="space-y-3">
        <h3 className="font-bold text-sm">{editId ? "Edit program" : "Add program"}</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <SelectField label="Faculty" value={form.faculty_id} onChange={(e) => setForm((f) => ({ ...f, faculty_id: e.target.value }))}>
            <option value="">Choose faculty</option>
            {faculties.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </SelectField>
          <TextField label="Program name" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} required />
          <TextField label="Code (optional)" value={form.code} onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))} hint="e.g. BSC-CS" />
          <SelectField label="Level" value={form.level} onChange={(e) => setForm((f) => ({ ...f, level: e.target.value }))}>
            {["CERTIFICATE", "DIPLOMA", "BACHELORS", "POSTGRADUATE_DIPLOMA", "MASTERS", "PHD", "OTHER"].map((l) => (
              <option key={l} value={l}>{l.replace(/_/g, " ")}</option>
            ))}
          </SelectField>
          <TextField label="Duration (years, optional)" type="number" value={form.duration_years} onChange={(e) => setForm((f) => ({ ...f, duration_years: e.target.value }))} min={1} max={8} />
        </div>
        {(create.isError || update.isError) && <Alert variant="error">{toUserMessage(create.error ?? update.error)}</Alert>}
        <div className="flex gap-2">
          <Button size="md" disabled={!form.faculty_id || !form.name.trim() || create.isPending || update.isPending} onClick={() => editId ? update.mutate() : create.mutate()}>
            {editId ? "Save" : "Add"}
          </Button>
          {editId && <Button size="md" variant="ghost" onClick={() => setEditId(null)}>Cancel</Button>}
        </div>
      </Card>

      {q.isPending && <p className="text-sm text-fg-muted">Loading…</p>}
      {q.isError && <Alert variant="error">{toUserMessage(q.error)}</Alert>}
      {q.data && (
        <div className="overflow-x-auto rounded-card border border-line">
          <table className="min-w-full text-sm">
            <thead className="bg-surface">
              <tr>{["Name", "Faculty", "Level", "Code", "Active", "Actions"].map((h) => <th key={h} className="px-3 py-2 text-left font-semibold text-fg-muted">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-line">
              {q.data.length === 0 && <tr><td colSpan={6} className="px-3 py-4 text-center text-fg-muted">No programs yet.</td></tr>}
              {q.data.map((p) => (
                <tr key={p.id} className={p.is_active ? "" : "opacity-60"}>
                  <td className="px-3 py-2 font-semibold">{p.name}</td>
                  <td className="px-3 py-2 text-fg-muted text-xs">{facultyName(p.faculty_id)}</td>
                  <td className="px-3 py-2 text-fg-muted">{p.level.replace(/_/g, " ")}</td>
                  <td className="px-3 py-2 font-mono">{p.code ?? "—"}</td>
                  <td className="px-3 py-2">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${p.is_active ? "bg-accent/10 text-accent" : "bg-surface text-fg-muted border border-line"}`}>
                      {p.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex gap-1">
                      <Button size="md" variant="ghost" onClick={() => startEdit(p)}>Edit</Button>
                      <button onClick={() => toggleActive.mutate({ id: p.id, is_active: !p.is_active })} className="text-xs text-secondary hover:underline px-2">
                        {p.is_active ? "Deactivate" : "Activate"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Course management ────────────────────────────────────────────────────────

function CourseSection({
  institutionId,
  faculties,
}: {
  institutionId: string;
  faculties: Faculty[];
}) {
  const qc = useQueryClient();
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState({ faculty_id: "", code: "", title: "", credit_units: "" });
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [draftQ, setDraftQ] = useState("");
  const [facultyFilter, setFacultyFilter] = useState("");

  const courses = useQuery({
    queryKey: ["catalog", "courses", institutionId, facultyFilter, q, page],
    queryFn: ({ signal }) => listCourses({
      institution_id: institutionId,
      faculty_id: facultyFilter || undefined,
      q: q || undefined,
      page,
      page_size: 20,
    }, signal),
    enabled: !!institutionId,
    placeholderData: keepPreviousData,
  });

  const create = useMutation({
    mutationFn: () => createCourse({
      faculty_id: form.faculty_id,
      code: form.code,
      title: form.title,
      credit_units: form.credit_units ? parseInt(form.credit_units, 10) : null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["catalog", "courses", institutionId] });
      setForm((f) => ({ ...f, code: "", title: "", credit_units: "" }));
    },
  });

  const update = useMutation({
    mutationFn: () => updateCourse(editId!, {
      title: form.title,
      credit_units: form.credit_units ? parseInt(form.credit_units, 10) : null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["catalog", "courses", institutionId] });
      setEditId(null);
    },
  });

  const toggleActive = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) => updateCourse(id, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["catalog", "courses", institutionId] }),
  });

  function startEdit(c: CourseRow) {
    setEditId(c.id);
    setForm({ faculty_id: c.faculty_id, code: c.code, title: c.title, credit_units: c.credit_units?.toString() ?? "" });
  }

  return (
    <div className="space-y-4">
      <Card className="space-y-3">
        <h3 className="font-bold text-sm">{editId ? "Edit course" : "Add course"}</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <SelectField label="Faculty" value={form.faculty_id} onChange={(e) => setForm((f) => ({ ...f, faculty_id: e.target.value }))}>
            <option value="">Choose faculty</option>
            {faculties.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </SelectField>
          <TextField label="Course code" value={form.code} onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))} hint="e.g. CSC 101" disabled={!!editId} required />
          <TextField label="Title" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} required />
          <TextField label="Credit units (optional)" type="number" value={form.credit_units} onChange={(e) => setForm((f) => ({ ...f, credit_units: e.target.value }))} min={0} max={30} />
        </div>
        {(create.isError || update.isError) && <Alert variant="error">{toUserMessage(create.error ?? update.error)}</Alert>}
        <div className="flex gap-2">
          <Button size="md"
            disabled={(!editId && !form.faculty_id) || !form.code.trim() || !form.title.trim() || create.isPending || update.isPending}
            onClick={() => editId ? update.mutate() : create.mutate()}
          >
            {editId ? "Save" : "Add course"}
          </Button>
          {editId && <Button size="md" variant="ghost" onClick={() => setEditId(null)}>Cancel</Button>}
        </div>
      </Card>

      <div className="flex flex-wrap gap-3">
        <div className="flex-1 max-w-xs">
          <SelectField label="Filter by faculty" value={facultyFilter} onChange={(e) => { setFacultyFilter(e.target.value); setPage(1); }}>
            <option value="">All faculties</option>
            {faculties.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </SelectField>
        </div>
        <form className="flex gap-2 items-end" onSubmit={(e) => { e.preventDefault(); setQ(draftQ); setPage(1); }}>
          <TextField label="Search courses" type="search" value={draftQ} onChange={(e) => setDraftQ(e.target.value)} placeholder="Code or title" />
          <Button type="submit" className="self-end min-h-11">Search</Button>
        </form>
      </div>

      {courses.isPending && <p className="text-sm text-fg-muted">Loading courses…</p>}
      {courses.isError && <Alert variant="error">{toUserMessage(courses.error)}</Alert>}
      {courses.data && (
        <>
          <p className="text-xs text-fg-muted" role="status">{courses.data.meta.total} course{courses.data.meta.total !== 1 ? "s" : ""}</p>
          <div className="overflow-x-auto rounded-card border border-line">
            <table className="min-w-full text-sm">
              <thead className="bg-surface">
                <tr>{["Code", "Title", "Credits", "Active", "Actions"].map((h) => <th key={h} className="px-3 py-2 text-left font-semibold text-fg-muted">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-line">
                {courses.data.items.length === 0 && <tr><td colSpan={5} className="px-3 py-4 text-center text-fg-muted">No courses found.</td></tr>}
                {courses.data.items.map((c) => (
                  <tr key={c.id} className={c.is_active ? "" : "opacity-60"}>
                    <td className="px-3 py-2 font-mono font-semibold">{c.code}</td>
                    <td className="px-3 py-2">{c.title}</td>
                    <td className="px-3 py-2 text-fg-muted">{c.credit_units ?? "—"}</td>
                    <td className="px-3 py-2">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${c.is_active ? "bg-accent/10 text-accent" : "bg-surface text-fg-muted border border-line"}`}>
                        {c.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex gap-1 flex-wrap">
                        <Button size="md" variant="ghost" onClick={() => startEdit(c)}>Edit</Button>
                        <button onClick={() => toggleActive.mutate({ id: c.id, is_active: !c.is_active })} className="text-xs text-secondary hover:underline px-2">
                          {c.is_active ? "Deactivate" : "Activate"}
                        </button>
                        <Link to={`/resources?course_id=${c.id}&institution_id=${c.institution_id}`} className="text-xs text-brand hover:underline px-2">
                          Resources →
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pageSize={20} total={courses.data.meta.total} onChange={setPage} />
        </>
      )}
    </div>
  );
}

// ─── Main AcademicManagementPanel ─────────────────────────────────────────────

type AcademicSection = "faculties" | "programs" | "courses";

export function AcademicManagementPanel() {
  const [institutionId, setInstitutionId] = useState("");
  const [section, setSection] = useState<AcademicSection>("faculties");

  const institutions = useQuery({
    queryKey: ["institutions"],
    queryFn: ({ signal }) => listAuthInstitutions(signal),
    staleTime: 300_000,
  });

  const faculties = useQuery({
    queryKey: ["catalog", "faculties", institutionId],
    queryFn: ({ signal }) => listFaculties(institutionId, signal),
    enabled: !!institutionId,
    staleTime: 60_000,
  });

  const sections: { id: AcademicSection; label: string }[] = [
    { id: "faculties", label: "Faculties / Schools" },
    { id: "programs", label: "Programs" },
    { id: "courses", label: "Courses" },
  ];

  return (
    <div className="space-y-6">
      <div className="max-w-xs">
        <SelectField
          label="University"
          value={institutionId}
          onChange={(e) => { setInstitutionId(e.target.value); }}
        >
          <option value="">Choose university</option>
          {institutions.data?.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
        </SelectField>
      </div>

      {!institutionId && (
        <p className="text-fg-muted">Choose a university to manage its academic structure.</p>
      )}

      {institutionId && (
        <>
          <div className="flex gap-1 border-b border-line pb-2">
            {sections.map((s) => (
              <button
                key={s.id}
                onClick={() => setSection(s.id)}
                className={`rounded-control px-4 py-1.5 text-sm font-semibold transition-colors ${
                  section === s.id ? "bg-primary text-white" : "text-fg-muted hover:bg-surface"
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>

          {section === "faculties" && <FacultySection institutionId={institutionId} />}
          {section === "programs" && (
            <ProgramSection
              institutionId={institutionId}
              faculties={faculties.data ?? []}
            />
          )}
          {section === "courses" && (
            <CourseSection
              institutionId={institutionId}
              faculties={faculties.data ?? []}
            />
          )}
        </>
      )}
    </div>
  );
}
