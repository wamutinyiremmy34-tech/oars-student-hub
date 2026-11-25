import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { TextField, PasswordField } from "@/components/ui/Field";
import { useAuth } from "@/features/auth/auth-context";
import { updateProfile } from "@/features/auth/api";
import { apiFetch } from "@/lib/api/client";
import { toUserMessage } from "@/lib/api/errors";
import { z } from "zod";

const messageSchema = z.object({ message: z.string() });

// ─── Change-password form ────────────────────────────────────────────────────

function ChangePasswordForm({ onClose }: { onClose: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [localError, setLocalError] = useState("");

  const mutation = useMutation({
    mutationFn: () => {
      if (next !== confirm) throw new Error("Passwords don't match.");
      if (next.length < 8) throw new Error("New password must be at least 8 characters.");
      return apiFetch("/auth/change-password", {
        method: "POST",
        body: { current_password: current, new_password: next },
        schema: messageSchema,
      });
    },
    onSuccess: () => { onClose(); },
    onError: (err) => setLocalError(toUserMessage(err)),
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLocalError("");
    if (next !== confirm) { setLocalError("Passwords don't match."); return; }
    mutation.mutate();
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <PasswordField label="Current password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
      <PasswordField label="New password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" required hint="At least 8 characters" />
      <PasswordField label="Confirm new password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required />
      {localError && <Alert variant="error">{localError}</Alert>}
      {mutation.isSuccess && <Alert variant="success">Password changed successfully.</Alert>}
      <div className="flex gap-2">
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "Changing…" : "Change password"}
        </Button>
        <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
      </div>
    </form>
  );
}

// ─── Edit-profile form ────────────────────────────────────────────────────────

function EditProfileForm({
  initialName,
  initialPhone,
  onClose,
}: {
  initialName: string;
  initialPhone: string | null;
  onClose: () => void;
}) {
  const [name, setName] = useState(initialName);
  const [phone, setPhone] = useState(initialPhone ?? "");

  const mutation = useMutation({
    mutationFn: () => {
      if (!name.trim()) throw new Error("Full name cannot be empty.");
      return updateProfile({ full_name: name.trim(), phone: phone.trim() });
    },
    onSuccess: () => { onClose(); },
  });

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); mutation.mutate(); }}
      className="space-y-3"
    >
      <TextField
        label="Full name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoComplete="name"
        required
      />
      <TextField
        label="Phone number (optional)"
        type="tel"
        value={phone}
        onChange={(e) => setPhone(e.target.value)}
        autoComplete="tel"
        hint="Leave blank to remove"
      />
      {mutation.isError && <Alert variant="error">{toUserMessage(mutation.error)}</Alert>}
      {mutation.isSuccess && <Alert variant="success">Profile updated.</Alert>}
      <div className="flex gap-2">
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "Saving…" : "Save changes"}
        </Button>
        <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
      </div>
    </form>
  );
}

// ─── Account page ─────────────────────────────────────────────────────────────

export function AccountPage() {
  const { state, signOut, refreshMe } = useAuth();
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [showEditProfile, setShowEditProfile] = useState(false);

  if (state.status !== "authenticated") return null;

  const { user, student_profile, roles } = state.me;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-extrabold">Your account</h1>

      {/* Profile */}
      <Card className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold">Profile</h2>
          {!showEditProfile && (
            <Button variant="ghost" size="md" onClick={() => setShowEditProfile(true)}>
              Edit
            </Button>
          )}
        </div>

        {showEditProfile ? (
          <EditProfileForm
            initialName={user.full_name}
            initialPhone={user.phone}
            onClose={async () => {
              await refreshMe();
              setShowEditProfile(false);
            }}
          />
        ) : (
          <dl className="grid gap-3 sm:grid-cols-2">
            <div>
              <dt className="text-sm text-fg-muted">Full name</dt>
              <dd className="font-semibold">{user.full_name}</dd>
            </div>
            <div>
              <dt className="text-sm text-fg-muted">Email</dt>
              <dd className="font-semibold break-all">{user.email}</dd>
            </div>
            <div>
              <dt className="text-sm text-fg-muted">Phone</dt>
              <dd className="font-semibold">{user.phone ?? <span className="text-fg-muted italic">Not set</span>}</dd>
            </div>
            <div>
              <dt className="text-sm text-fg-muted">Email verified</dt>
              <dd className="font-semibold">{user.email_verified ? "✓ Verified" : "Not yet verified"}</dd>
            </div>
          </dl>
        )}

        {!user.email_verified && !showEditProfile && (
          <Alert variant="info">
            Your email isn't verified yet. Check your inbox for the verification link.
          </Alert>
        )}
      </Card>

      {/* Student profile */}
      {student_profile && (
        <Card className="space-y-4">
          <h2 className="text-lg font-bold">Student profile</h2>
          <dl className="grid gap-3 sm:grid-cols-2">
            {student_profile.student_number && (
              <div>
                <dt className="text-sm text-fg-muted">Student number</dt>
                <dd className="font-semibold">{student_profile.student_number}</dd>
              </div>
            )}
            {student_profile.year_of_study && (
              <div>
                <dt className="text-sm text-fg-muted">Year of study</dt>
                <dd className="font-semibold">Year {student_profile.year_of_study}</dd>
              </div>
            )}
          </dl>
          <p className="text-xs text-fg-muted">
            To update your student number or year of study, contact your institution administrator.
          </p>
        </Card>
      )}

      {/* Roles */}
      <Card className="space-y-3">
        <h2 className="text-lg font-bold">Roles</h2>
        {roles.length === 0 ? (
          <p className="text-fg-muted text-sm">No roles assigned.</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {roles.map((r, i) => (
              <li key={i} className="rounded-full border border-line px-3 py-1 text-sm font-semibold">
                {r.role}
                {r.institution_id && <span className="ml-1 text-xs text-fg-muted">(institution)</span>}
              </li>
            ))}
          </ul>
        )}
        <p className="text-xs text-fg-muted">Roles are managed by administrators. You cannot change your own role.</p>
      </Card>

      {/* Security */}
      <Card className="space-y-4">
        <h2 className="text-lg font-bold">Security</h2>
        {showChangePassword ? (
          <ChangePasswordForm onClose={() => setShowChangePassword(false)} />
        ) : (
          <Button variant="secondary" onClick={() => setShowChangePassword(true)}>
            Change password
          </Button>
        )}
      </Card>

      {/* Sign out */}
      <Card className="space-y-3">
        <h2 className="text-lg font-bold">Session</h2>
        <p className="text-sm text-fg-muted">
          Signing out clears all your local session data. You'll need to sign in again.
        </p>
        <Button variant="danger" onClick={() => void signOut()}>
          Sign out of this device
        </Button>
      </Card>
    </div>
  );
}
