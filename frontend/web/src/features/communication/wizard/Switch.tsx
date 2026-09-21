import { cn } from "@fusion-flow/ui";

/**
 * A minimal on/off pill toggle. This codebase's shared `@fusion-flow/ui`
 * package has no `Switch` primitive today (every existing boolean setting
 * uses a plain `<input type="checkbox">` - see e.g.
 * `frontend/admin/src/features/feature-flags/FeatureFlagsPage.tsx`); kept
 * local to this wizard feature rather than added to the shared package,
 * since a real Switch visual (vs. a checkbox) is specifically what the
 * Profiterasoft reference this feature was built against uses for its
 * Auto-Like/Auto-Reply/... toggle rows, and promoting it to the shared
 * library is a separate decision for whoever owns that package.
 */
interface SwitchProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  "aria-label"?: string;
}

export function Switch({ checked, onCheckedChange, disabled, ...rest }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors",
        checked ? "bg-accent" : "bg-muted",
        disabled && "cursor-not-allowed opacity-50",
      )}
      {...rest}
    >
      <span
        className={cn(
          "inline-block h-4 w-4 rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-4" : "translate-x-0.5",
        )}
      />
    </button>
  );
}
