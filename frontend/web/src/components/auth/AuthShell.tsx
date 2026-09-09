import type { ReactNode } from "react";
import { Sparkles } from "lucide-react";

export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-8 bg-background px-4">
      <div className="flex items-center gap-2">
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-accent text-accent-foreground">
          <Sparkles className="h-5 w-5" />
        </div>
        <span className="text-lg font-semibold text-foreground">fusion-flow</span>
      </div>
      {children}
    </div>
  );
}
