export type ThemePreference = "light" | "dark" | "system";

export const THEME_STORAGE_KEY = "oars.theme";
const PREFERENCES: readonly ThemePreference[] = ["light", "dark", "system"];

export function readPreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return PREFERENCES.includes(stored as ThemePreference) ? (stored as ThemePreference) : "system";
  } catch {
    return "system";
  }
}

export function savePreference(preference: ThemePreference): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Storage unavailable (private mode / quota): the preference simply won't persist.
  }
}

export function systemPrefersDark(): boolean {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}

export function resolveTheme(preference: ThemePreference, prefersDark: boolean): "light" | "dark" {
  if (preference === "system") return prefersDark ? "dark" : "light";
  return preference;
}

export function applyTheme(preference: ThemePreference): void {
  const dark = resolveTheme(preference, systemPrefersDark()) === "dark";
  document.documentElement.classList.toggle("dark", dark);
}

export function nextPreference(current: ThemePreference): ThemePreference {
  if (current === "light") return "dark";
  if (current === "dark") return "system";
  return "light";
}
