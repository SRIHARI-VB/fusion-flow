import type { ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { cn } from "@fusion-flow/ui";

/**
 * Inline banner for PARTIAL degradation - the page still works, but one
 * capability (e.g. a customer picker) is unavailable because a module it
 * depends on isn't accessible. Use `RequireModule` when the whole page is
 * blocked instead.
 */
export function ModuleAccessNotice({
  title,
  children,
  className,
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      role="note"
      className={cn(
        "flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900",
        className,
      )}
    >
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <div>
        {title && <p className="font-medium">{title}</p>}
        <p>{children}</p>
      </div>
    </div>
  );
}
