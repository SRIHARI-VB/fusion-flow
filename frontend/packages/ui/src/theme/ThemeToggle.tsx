import * as React from "react";
import { Sun, Moon, Monitor } from "lucide-react";
import { useTheme, type Theme } from "./ThemeProvider";
import { Button } from "../components/Button";

const order: Theme[] = ["light", "dark", "system"];

const icons: Record<Theme, React.ComponentType<{ className?: string }>> = {
  light: Sun,
  dark: Moon,
  system: Monitor,
};

const labels: Record<Theme, string> = {
  light: "Light theme",
  dark: "Dark theme",
  system: "System theme",
};

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme();
  const Icon = icons[theme];

  function cycle() {
    const idx = order.indexOf(theme);
    setTheme(order[(idx + 1) % order.length]);
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className={className}
      onClick={cycle}
      aria-label={`Toggle theme (current: ${labels[theme]})`}
      title={labels[theme]}
    >
      <Icon className="h-4 w-4" />
    </Button>
  );
}
