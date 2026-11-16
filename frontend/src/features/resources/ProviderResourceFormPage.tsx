import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router-dom";
import { z } from "zod";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SelectField, TextField } from "@/components/ui/Field";
import { listInstitutions } from "@/features/auth/api";
import { CoursePicker } from "@/features/resources/CoursePicker";
import { StatusBadge } from "@/features/resources/Badges";
import {
  createResource,
  getResource,
  listCategories,
  runLifecycle,
  updateResource,
  uploadVersion,
  type CourseRef,
  type ResourceInput,
} from "@/features/resources/api";
import { toUserMessage } from "@/lib/api/errors";
import { formatBytes } from "@/lib/format";

export const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;
const ACCEPT = ".pdf,.docx,.pptx,.xlsx,.png,.jpg,.jpeg,.txt";

const schema = z
  .object({
    institution_id: z.string().min(1, "Choose a university"),
    category_id: z.string().min(1, "Choose a type"),
    title: z.string().trim().min(3, "Use at least 3 characters").max(200),
    description: z.string().trim().max(5000),
    preview_text: z.string().trim().max(1000),
    access_type: z.enum(["FREE", "PREMIUM"]),
    price_ugx: z.string().trim(),
    tags: z.string().trim(),
  })
  .refine((v) => v.access_type === "FREE" || /^[1-9][0-9]{0,8}$/.test(v.price_ugx), {
    path: ["price_ugx"],
    message: "Enter a whole number of shillings, for example 5000",
  });
type Values = z.infer<typeof schema>;

function parseTags(text: string): string[] {
  return [...new Set(text.split(",").map((t) => t.trim().toLowerCase()).filter(Boolean))];
}

export function ProviderResourceFormPage() {
  const { id } = useParams();
  const editing = id !== undefined;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [courses, setCourses] = useState<CourseRef[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);

  const institutions = useQuery({ queryKey: ["institutions"], queryFn: ({ signal }) => listInstitutions(signal), staleTime: 300_000 });
  const categories = useQuery({ queryKey: ["categories"], queryFn: ({ signal }) => listCategories(signal), staleTime: 300_000 });
  const existing = useQuery({
    queryKey: ["resources", "detail", id],
    queryFn: ({ signal }) => getResource(id ?? "", signal),
    enabled: editing,
  });

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { institution_id: "", category_id: "", title: "", description: "", preview_text: "", access_type: "FREE", price_ugx: "", tags: "" },
  });
  const { register, handleSubmit, watch, reset, formState } = form;
  const access = watch("access_type");
  const institutionId = watch("institution_id");

  useEffect(() => {
    const r = existing.data;
    if (!r) return;
    reset({
      institution_id: r.institution_id, category_id: r.category.id, title: r.title, description: r.description,
      preview_text: r.preview_text ?? "", access_type: r.access_type, price_ugx: r.price_ugx ? String(r.price_ugx) : "", tags: r.tags.join(", "),
    });
    setCourses(r.courses);
  }, [existing.data, reset]);

  const editable = !editing || existing.data?.status === "DRAFT" || existing.data?.status === "REJECTED";

  function toInput(v: Values): ResourceInput {
    return {
      institution_id: v.institution_id,
      category_id: v.category_id,
      title: v.title,
      description: v.description,
      preview_text: v.preview_text || undefined,
      access_type: v.access_type,
      price_ugx: v.access_type === "PREMIUM" ? Number(v.price_ugx) : undefined,
      tags: parseTags(v.tags),
      course_ids: courses.map((c) => c.id),
    };
  }

  const save = useMutation({
    mutationFn: async (v: Values) => {
      const input = toInput(v);
      if (editing && id) {
        const { institution_id: _ignored, ...patch } = input;
        void _ignored;
        return updateResource(id, { ...patch, price_ugx: input.price_ugx });
      }
      return createResource(input);
    },
    onSuccess: async (resource) => {
      await queryClient.invalidateQueries({ queryKey: ["resources"] });
      if (!editing) navigate(`/provider/resources/${resource.id}`, { replace: true });
    },
  });

  const upload = useMutation({
    mutationFn: (file: File) => uploadVersion(id ?? "", file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["resources"] }),
  });
  const submit = useMutation({
    mutationFn: () => runLifecycle(id ?? "", "submit"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["resources"] }),
  });

  function onFileChosen(file: File | undefined) {
    setFileError(null);
    if (!file) return;
    if (file.size > MAX_UPLOAD_BYTES) {
      setFileError(`That file is ${formatBytes(file.size)}. The limit is ${formatBytes(MAX_UPLOAD_BYTES)}.`);
      return;
    }
    upload.mutate(file);
    if (fileInput.current) fileInput.current.value = "";
  }

  if (editing && existing.isPending) return <p role="status" className="text-fg-muted">Loading…</p>;
  if (editing && existing.isError) return <Alert variant="error">{toUserMessage(existing.error)}</Alert>;
  const resource = existing.data;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-extrabold">{editing ? "Edit resource" : "New resource"}</h1>
        {resource && <StatusBadge status={resource.status} />}
        <Link to="/provider/resources" className="ml-auto text-sm font-semibold text-brand underline">Back to my resources</Link>
      </div>

      {resource?.latest_review?.decision === "REJECTED" && resource.status === "REJECTED" && (
        <Alert variant="error">Rejected by a reviewer: {resource.latest_review.reason}. Edit and re-submit.</Alert>
      )}
      {editing && !editable && <Alert variant="info">This resource is {resource?.status.toLowerCase().replace("_", " ")} and can't be edited right now.</Alert>}

      <Card>
        <form onSubmit={handleSubmit((v) => save.mutate(v))} noValidate className="space-y-4">
          <fieldset disabled={!editable} className="space-y-4">
            {editing ? (
              // Not a disabled input: react-hook-form drops disabled fields from the submitted values.
              <p className="text-sm">
                <span className="font-semibold">University: </span>
                {existing.data?.institution_name}
              </p>
            ) : (
              <SelectField label="University" error={formState.errors.institution_id?.message} {...register("institution_id")}>
                <option value="">Choose a university</option>
                {institutions.data?.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
              </SelectField>
            )}
            <SelectField label="Type" error={formState.errors.category_id?.message} {...register("category_id")}>
              <option value="">Choose a type</option>
              {categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </SelectField>
            <TextField label="Title" error={formState.errors.title?.message} {...register("title")} />
            <div className="space-y-1">
              <label htmlFor="description" className="block text-sm font-semibold">Description</label>
              <textarea id="description" className="min-h-28 w-full rounded-control border border-line bg-raised p-3" {...register("description")} />
            </div>
            <TextField label="Preview text (shown to everyone, even for premium)" hint="A short sample or summary." {...register("preview_text")} />
            <SelectField label="Access" {...register("access_type")}>
              <option value="FREE">Free</option>
              <option value="PREMIUM">Premium (paid)</option>
            </SelectField>
            {access === "PREMIUM" && (
              <TextField label="Price (UGX)" inputMode="numeric" error={formState.errors.price_ugx?.message} {...register("price_ugx")} />
            )}
            <TextField label="Tags (comma separated)" hint="Up to 10, for example calculus, year-1" {...register("tags")} />
            <CoursePicker institutionId={institutionId} value={courses} onChange={setCourses} />
          </fieldset>
          {save.isError && <Alert variant="error">{toUserMessage(save.error)}</Alert>}
          {save.isSuccess && editing && <Alert variant="success">Saved.</Alert>}
          {editable && (
            <Button type="submit" size="lg" disabled={save.isPending}>
              {save.isPending ? "Saving…" : editing ? "Save changes" : "Create draft"}
            </Button>
          )}
        </form>
      </Card>

      {resource && (
        <Card className="space-y-4" aria-label="Files">
          <h2 className="text-lg font-bold">Files</h2>
          {resource.versions.length === 0 ? (
            <p className="text-fg-muted">No file uploaded yet.</p>
          ) : (
            <ul className="space-y-1">
              {resource.versions.map((v) => (
                <li key={v.id} className="text-sm">
                  v{v.version_number} · {v.filename} · {formatBytes(v.size_bytes)}{v.is_current ? " · published version" : ""}
                </li>
              ))}
            </ul>
          )}
          {editable && (
            <div className="space-y-2">
              <label htmlFor="file" className="block text-sm font-semibold">Upload a new version (PDF, Word, PowerPoint, Excel, image or text, up to {formatBytes(MAX_UPLOAD_BYTES)})</label>
              <input ref={fileInput} id="file" type="file" accept={ACCEPT} onChange={(e) => onFileChosen(e.target.files?.[0])} className="block w-full text-sm" />
              {fileError && <Alert variant="error">{fileError}</Alert>}
              {upload.isPending && <p role="status" className="text-fg-muted">Uploading…</p>}
              {upload.isError && <Alert variant="error">{toUserMessage(upload.error)}</Alert>}
              {upload.isSuccess && <Alert variant="success">File uploaded.</Alert>}
            </div>
          )}
          {resource.status === "DRAFT" && (
            <div className="space-y-2">
              <Button disabled={resource.versions.length === 0 || submit.isPending} onClick={() => submit.mutate()}>
                Submit for review
              </Button>
              {resource.versions.length === 0 && <p className="text-sm text-fg-muted">Upload a file before submitting.</p>}
              {submit.isError && <Alert variant="error">{toUserMessage(submit.error)}</Alert>}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
