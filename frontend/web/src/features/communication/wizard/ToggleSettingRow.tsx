import type { LucideIcon } from "lucide-react";
import { Switch } from "./Switch";

/** Icon + label + description + Switch, all on one row - the Auto-Like /
 * Auto-Reply / Auto-Hide / ... row shape from the Profiterasoft reference. */
interface ToggleSettingRowProps {
  icon: LucideIcon;
  label: string;
  description: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
}

export function ToggleSettingRow({
  icon: Icon,
  label,
  description,
  checked,
  onCheckedChange,
  disabled,
}: ToggleSettingRowProps) {
  return (
    <div className="flex items-start gap-3 rounded-md border border-border p-3">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="flex-1">
        <p className="text-sm font-medium text-foreground">{label}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} disabled={disabled} aria-label={label} />
    </div>
  );
}
