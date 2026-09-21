import { cn } from "@fusion-flow/ui";

/**
 * A selectable card with a title + one-line description - the "Exact
 * Match" / "Contains" / "Starts With" style picker from the Profiterasoft
 * reference, used in place of a plain `<select>` wherever the options
 * benefit from an explanatory line (matching methods, toggle groups, ...).
 */
interface OptionPickerCardProps {
  title: string;
  description: string;
  selected: boolean;
  onSelect: () => void;
}

export function OptionPickerCard({ title, description, selected, onSelect }: OptionPickerCardProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex flex-col gap-0.5 rounded-md border p-3 text-left transition-colors",
        selected ? "border-accent bg-accent-soft" : "border-border hover:bg-muted",
      )}
    >
      <span className={cn("text-sm font-medium", selected ? "text-accent" : "text-foreground")}>{title}</span>
      <span className="text-xs text-muted-foreground">{description}</span>
    </button>
  );
}
