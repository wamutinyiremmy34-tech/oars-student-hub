import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Card } from "@/components/ui/Card";
import { SelectField } from "@/components/ui/Field";
import { Pagination } from "@/components/ui/Pagination";
import { listInstitutions } from "@/features/auth/api";
import { listCourses, listFaculties, listPrograms } from "@/features/catalog/api";
import { toUserMessage } from "@/lib/api/errors";

const PAGE_SIZE = 20;

/** Browse the academic structure: university → faculty/school/college → program → courses → resources. */
export function CatalogPage() {
  const [institutionId, setInstitutionId] = useState("");
  const [facultyId, setFacultyId] = useState("");
  const [programId, setProgramId] = useState("");
  const [page, setPage] = useState(1);

  const institutions = useQuery({ queryKey: ["institutions"], queryFn: ({ signal }) => listInstitutions(signal), staleTime: 300_000 });
  const faculties = useQuery({
    queryKey: ["catalog", "faculties", institutionId],
    queryFn: ({ signal }) => listFaculties(institutionId, signal),
    enabled: institutionId !== "",
  });
  const programs = useQuery({
    queryKey: ["catalog", "programs", institutionId, facultyId],
    queryFn: ({ signal }) => listPrograms(institutionId, facultyId || undefined, signal),
    enabled: institutionId !== "",
  });
  const courses = useQuery({
    queryKey: ["catalog", "courses", institutionId, facultyId, programId, page],
    queryFn: ({ signal }) =>
      listCourses(
        { institution_id: institutionId, faculty_id: facultyId || undefined, program_id: programId || undefined, page, page_size: PAGE_SIZE },
        signal,
      ),
    enabled: institutionId !== "",
    placeholderData: keepPreviousData,
  });

  // Universities name their top-level units differently (faculty, school, college...), so use the data's own label.
  const unitLabel = faculties.data?.[0]?.kind ? faculties.data[0].kind.toLowerCase() : "faculty";

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-extrabold">Browse by course</h1>
      <div className="grid gap-3 sm:grid-cols-3">
        <SelectField label="University" value={institutionId} onChange={(e) => { setInstitutionId(e.target.value); setFacultyId(""); setProgramId(""); setPage(1); }}>
          <option value="">Choose your university</option>
          {institutions.data?.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
        </SelectField>
        <SelectField label={`Faculty / school (${unitLabel})`} value={facultyId} disabled={!institutionId} onChange={(e) => { setFacultyId(e.target.value); setProgramId(""); setPage(1); }}>
          <option value="">All</option>
          {faculties.data?.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </SelectField>
        <SelectField label="Program" value={programId} disabled={!institutionId} onChange={(e) => { setProgramId(e.target.value); setPage(1); }}>
          <option value="">All programs</option>
          {programs.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </SelectField>
      </div>

      {!institutionId && <p className="text-fg-muted">Choose a university to see its courses.</p>}
      {courses.isError && <Alert variant="error">{toUserMessage(courses.error)}</Alert>}
      {courses.data && (
        <section className="space-y-3">
          <p role="status" className="text-sm text-fg-muted">
            {courses.data.meta.total === 0 ? "No courses found." : `${courses.data.meta.total} courses`}
          </p>
          <ul className="grid gap-3 md:grid-cols-2">
            {courses.data.items.map((course) => (
              <li key={course.id}>
                <Card className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-bold">{course.code}</p>
                    <p className="text-sm text-fg-muted">{course.title}</p>
                  </div>
                  <Link to={`/resources?course_id=${course.id}&institution_id=${course.institution_id}`} className="shrink-0 font-semibold text-brand underline">
                    Find resources
                  </Link>
                </Card>
              </li>
            ))}
          </ul>
          <Pagination page={page} pageSize={PAGE_SIZE} total={courses.data.meta.total} onChange={setPage} />
        </section>
      )}
    </div>
  );
}
