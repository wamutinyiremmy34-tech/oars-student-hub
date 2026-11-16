import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/Field";
import { listCourses } from "@/features/catalog/api";
import type { CourseRef } from "@/features/resources/api";

/** Links a resource to courses of ONE institution (the API rejects courses from any other). */
export function CoursePicker({
  institutionId,
  value,
  onChange,
}: {
  institutionId: string;
  value: CourseRef[];
  onChange: (courses: CourseRef[]) => void;
}) {
  const [text, setText] = useState("");
  const search = useQuery({
    queryKey: ["catalog", "course-search", institutionId, text],
    queryFn: ({ signal }) => listCourses({ institution_id: institutionId, q: text, page_size: 6 }, signal),
    enabled: institutionId !== "" && text.trim().length >= 2,
  });
  const chosen = new Set(value.map((c) => c.id));

  return (
    <div className="space-y-2">
      <TextField
        label="Courses this resource belongs to"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Search by course code or title"
        hint={institutionId ? "Type at least 2 characters." : "Choose a university first."}
        disabled={!institutionId}
      />
      {value.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label="Selected courses">
          {value.map((course) => (
            <li key={course.id} className="flex items-center gap-1 rounded-full border border-line px-3 py-1 text-sm">
              {course.code}
              <button type="button" aria-label={`Remove ${course.code}`} className="font-bold" onClick={() => onChange(value.filter((c) => c.id !== course.id))}>
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      {search.data && (
        <ul className="space-y-1" aria-label="Course search results">
          {search.data.items
            .filter((c) => !chosen.has(c.id))
            .map((course) => (
              <li key={course.id}>
                <Button variant="ghost" className="w-full justify-start" onClick={() => onChange([...value, { id: course.id, code: course.code, title: course.title }])}>
                  Add {course.code} · {course.title}
                </Button>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
