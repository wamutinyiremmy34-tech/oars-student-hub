import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/Button";
import { setBookmark } from "@/features/resources/api";
import { useAuth } from "@/features/auth/auth-context";

/** Renders nothing for visitors: bookmarks belong to an account (the API enforces this too). */
export function BookmarkButton({ resourceId, bookmarked }: { resourceId: string; bookmarked: boolean }) {
  const { state } = useAuth();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => setBookmark(resourceId, !bookmarked),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["resources"] }).then(() => queryClient.invalidateQueries({ queryKey: ["bookmarks"] })),
  });
  if (state.status !== "authenticated") return null;
  return (
    <Button
      variant="secondary"
      aria-pressed={bookmarked}
      disabled={mutation.isPending}
      onClick={() => mutation.mutate()}
    >
      {bookmarked ? "Saved ✓" : "Save"}
    </Button>
  );
}
