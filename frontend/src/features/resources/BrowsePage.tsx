import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { SelectField, TextField } from "@/components/ui/Field";
import { Pagination } from "@/components/ui/Pagination";
import { listInstitutions } from "@/features/auth/api";
import { listCategories, searchResources, type SearchQuery } from "@/features/resources/api";
import { ResourceCard } from "@/features/resources/ResourceCard";
import { toUserMessage } from "@/lib/api/errors";

const PAGE_SIZE = 12;

/** All filter state lives in the URL, so results are shareable, bookmarkable and survive the back button. */
export function BrowsePage() {
  const [params, setParams] = useSearchParams();
  const [draft, setDraft] = useState(params.get("q") ?? "");

  const query: SearchQuery = {
    q: params.get("q") ?? undefined,
    institution_id: params.get("institution_id") ?? undefined,
    category: params.get("category") ?? undefined,
    course_id: params.get("course_id") ?? undefined,
    access: (params.get("access") as SearchQuery["access"]) ?? undefined,
    sort: (params.get("sort") as SearchQuery["sort"]) ?? undefined,
    page: params.get("page") ? Number(params.get("page")) : undefined,
    page_size: PAGE_SIZE,
  };

  const results = useQuery({
    queryKey: ["resources", "search", query],
    queryFn: ({ signal }) => searchResources(query, signal),
    placeholderData: keepPreviousData,
  });
  const institutions = useQuery({ queryKey: ["institutions"], queryFn: ({ signal }) => listInstitutions(signal), staleTime: 300_000 });
  const categories = useQuery({ queryKey: ["categories"], queryFn: ({ signal }) => listCategories(signal), staleTime: 300_000 });

  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    if (!("page" in changes)) next.delete("page"); // any filter change returns to the first page
    setParams(next);
  }

  function onSearch(event: FormEvent) {
    event.preventDefault();
    update({ q: draft.trim() || null });
  }

  const total = results.data?.meta.total ?? 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-extrabold">Find resources</h1>

      <form onSubmit={onSearch} role="search" className="flex items-end gap-2">
        <div className="flex-1">
          <TextField label="Search notes, past papers and course codes" type="search" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="e.g. calculus or CSC1201" />
        </div>
        <Button type="submit" size="lg">
          Search
        </Button>
      </form>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <SelectField label="University" value={query.institution_id ?? ""} onChange={(e) => update({ institution_id: e.target.value || null })}>
          <option value="">All universities</option>
          {institutions.data?.map((i) => (
            <option key={i.id} value={i.id}>
              {i.name}
            </option>
          ))}
        </SelectField>
        <SelectField label="Type" value={query.category ?? ""} onChange={(e) => update({ category: e.target.value || null })}>
          <option value="">All types</option>
          {categories.data?.map((c) => (
            <option key={c.id} value={c.slug}>
              {c.name}
            </option>
          ))}
        </SelectField>
        <SelectField label="Price" value={query.access ?? ""} onChange={(e) => update({ access: e.target.value || null })}>
          <option value="">Free and premium</option>
          <option value="FREE">Free only</option>
          <option value="PREMIUM">Premium only</option>
        </SelectField>
        <SelectField label="Sort by" value={query.sort ?? ""} onChange={(e) => update({ sort: e.target.value || null })}>
          <option value="">{query.q ? "Best match" : "Newest"}</option>
          <option value="newest">Newest</option>
          <option value="title">Title A-Z</option>
        </SelectField>
      </div>

      {query.course_id && (
        <Alert variant="info">
          Showing resources for one course.{" "}
          <button type="button" className="underline" onClick={() => update({ course_id: null })}>
            Clear
          </button>
        </Alert>
      )}

      {results.isPending && (
        <p role="status" className="text-fg-muted">
          Loading resources…
        </p>
      )}
      {results.isError && (
        <div className="space-y-3">
          <Alert variant="error">{toUserMessage(results.error)}</Alert>
          <Button onClick={() => void results.refetch()}>Try again</Button>
        </div>
      )}
      {results.data && (
        <section aria-busy={results.isFetching} className="space-y-4">
          <p className="text-sm text-fg-muted" role="status">
            {total === 0 ? "No resources found." : `${total} resource${total === 1 ? "" : "s"} found`}
          </p>
          <ul className="grid gap-4 md:grid-cols-2">
            {results.data.items.map((resource) => (
              <li key={resource.id}>
                <ResourceCard resource={resource} />
              </li>
            ))}
          </ul>
          <Pagination page={query.page ?? 1} pageSize={PAGE_SIZE} total={total} onChange={(page) => update({ page: String(page) })} />
        </section>
      )}
    </div>
  );
}
