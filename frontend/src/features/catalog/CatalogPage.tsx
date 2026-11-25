import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Card } from "@/components/ui/Card";
import { SelectField } from "@/components/ui/Field";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { Pagination } from "@/components/ui/Pagination";
import { GraduationCap, ArrowRight, BookOpen } from "@/components/ui/Icon";
import { listInstitutions } from "@/features/auth/api";
import { listCourses, listFaculties, listPrograms } from "@/features/catalog/api";
import { toUserMessage } from "@/lib/api/errors";

const PAGE_SIZE = 20;

export function CatalogPage() {
  const [institutionId, setInstitutionId] = useState("");
  const [facultyId, setFacultyId]         = useState("");
  const [programId, setProgramId]         = useState("");
  const [page, setPage]                   = useState(1);

  const institutions = useQuery({
    queryKey: ["institutions"],
    queryFn:  ({ signal }) => listInstitutions(signal),
    staleTime: 300_000,
  });

  const faculties = useQuery({
    queryKey: ["catalog", "faculties", institutionId],
    queryFn:  ({ signal }) => listFaculties(institutionId, signal),
    enabled:  institutionId !== "",
  });

  const programs = useQuery({
    queryKey: ["catalog", "programs", institutionId, facultyId],
    queryFn:  ({ signal }) => listPrograms(institutionId, facultyId || undefined, signal),
    enabled:  institutionId !== "",
  });

  const courses = useQuery({
    queryKey: ["catalog", "courses", institutionId, facultyId, programId, page],
    queryFn:  ({ signal }) =>
      listCourses(
        {
          institution_id: institutionId,
          faculty_id:  facultyId   || undefined,
          program_id:  programId   || undefined,
          page,
          page_size:   PAGE_SIZE,
        },
        signal,
      ),
    enabled:        institutionId !== "",
    placeholderData: keepPreviousData,
  });

  const unitLabel = faculties.data?.[0]?.kind
    ? faculties.data[0].kind.toLowerCase()
    : "faculty";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold">Browse by course</h1>
        <p className="mt-1 text-sm text-fg-muted">
          Navigate the academic structure to find resources for your specific courses.
        </p>
      </div>

      {/* Filters */}
      <div className="grid gap-3 sm:grid-cols-3">
        <SelectField
          label="University"
          value={institutionId}
          onChange={(e) => {
            setInstitutionId(e.target.value);
            setFacultyId("");
            setProgramId("");
            setPage(1);
          }}
        >
          <option value="">Choose your university</option>
          {institutions.data?.map((i) => (
            <option key={i.id} value={i.id}>{i.name}</option>
          ))}
        </SelectField>

        <SelectField
          label={`Faculty / school (${unitLabel})`}
          value={facultyId}
          disabled={!institutionId}
          onChange={(e) => {
            setFacultyId(e.target.value);
            setProgramId("");
            setPage(1);
          }}
        >
          <option value="">All</option>
          {faculties.data?.map((f) => (
            <option key={f.id} value={f.id}>{f.name}</option>
          ))}
        </SelectField>

        <SelectField
          label="Program"
          value={programId}
          disabled={!institutionId}
          onChange={(e) => {
            setProgramId(e.target.value);
            setPage(1);
          }}
        >          <option value="">All programmes</option>
          {programs.data?.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </SelectField>
      </div>

      {/* Empty state — no university selected */}
      {!institutionId && (
        <div className="flex flex-col items-center gap-4 py-16 text-center">
          <div className="rounded-full bg-surface p-6">
            <GraduationCap size="xl" className="text-fg-muted" aria-hidden />
          </div>
          <div className="space-y-1">
            <p className="font-semibold">Choose a university to see its courses.</p>
            <p className="text-sm text-fg-muted max-w-sm">
              Browse the academic structure to find resources for your courses.
            </p>
          </div>
        </div>
      )}

      {/* Loading */}
      {courses.isPending && institutionId && (
        <div className="grid gap-3 md:grid-cols-2" aria-label="Loading courses" aria-busy="true">
          {Array.from({ length: 8 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      )}

      {/* Error */}
      {courses.isError && (
        <Alert variant="error">{toUserMessage(courses.error)}</Alert>
      )}

      {/* Results */}
      {courses.data && (
        <section className="space-y-4" aria-busy={courses.isFetching}>
          <p role="status" className="text-sm text-fg-muted">
            {courses.data.meta.total === 0
              ? "No courses found for the selected filters."
              : `${courses.data.meta.total.toLocaleString()} course${courses.data.meta.total === 1 ? "" : "s"}`}
          </p>

          {courses.data.items.length > 0 ? (
            <>
              <ul className="grid gap-3 md:grid-cols-2" aria-label="Courses">
                {courses.data.items.map((course) => (
                  <li key={course.id}>
                    <Card className="flex items-center justify-between gap-3 hover:shadow-lifted transition-shadow p-3">
                      <div className="flex items-start gap-3 min-w-0">
                        <div className="rounded-control bg-brand/10 p-2 shrink-0">
                          <BookOpen size="sm" className="text-brand" aria-hidden />
                        </div>
                        <div className="min-w-0">
                          <p className="font-bold text-sm">{course.code}</p>
                          <p className="text-sm text-fg-muted truncate">{course.title}</p>
                        </div>
                      </div>
                      <Link
                        to={`/resources?course_id=${course.id}&institution_id=${course.institution_id}`}
                        className="shrink-0 inline-flex items-center gap-1 text-sm font-semibold text-secondary hover:underline"
                      >
                        Find resources
                        <ArrowRight size="xs" aria-hidden />
                      </Link>
                    </Card>
                  </li>
                ))}
              </ul>

              <Pagination
                page={page}
                pageSize={PAGE_SIZE}
                total={courses.data.meta.total}
                onChange={setPage}
              />
            </>
          ) : (
            <div className="flex flex-col items-center gap-4 py-12 text-center">
              <GraduationCap size="lg" className="text-fg-muted" aria-hidden />
              <p className="text-fg-muted text-sm">No courses found for the selected filters.</p>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
