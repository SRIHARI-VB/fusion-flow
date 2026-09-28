import type { ReactNode } from "react";
import { Logo } from "@fusion-flow/ui";

export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-8 bg-background px-4">
      <div className="flex items-center gap-2">
        <Logo size={36} />
        <span className="text-lg font-semibold text-foreground">Stilltyping</span>
      </div>
      {children}
    </div>
  );
}
