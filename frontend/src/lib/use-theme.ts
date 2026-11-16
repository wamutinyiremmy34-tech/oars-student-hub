import { useCallback, useEffect, useState } from "react";
import {
  applyTheme,
  readPreference,
  savePreference,
  type ThemePreference,
} from "@/lib/theme";

export function useTheme() {
  const [preference, setPreferenceState] = useState<ThemePreference>(readPreference);

  useEffect(() => {
    applyTheme(preference);
    if (preference !== "system" || typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme("system");
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [preference]);

  const setPreference = useCallback((next: ThemePreference) => {
    savePreference(next);
    setPreferenceState(next);
  }, []);

  return { preference, setPreference };
}
