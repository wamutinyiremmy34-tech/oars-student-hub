import { Button } from "@/components/ui/Button";
import { nextPreference } from "@/lib/theme";
import { useTheme } from "@/lib/use-theme";

const LABELS = { light: "Light", dark: "Dark", system: "System" } as const;

export function ThemeToggle() {
  const { preference, setPreference } = useTheme();
  return (
    <Button
      variant="secondary"
      onClick={() => setPreference(nextPreference(preference))}
      title="Change colour theme"
    >
      Theme: {LABELS[preference]}
    </Button>
  );
}
