import { Check } from "lucide-react";
import { cn } from "@fusion-flow/ui";

/** "1 Keywords & Options — 2 Reply Material" style step header. */
interface WizardStepIndicatorProps {
  steps: string[];
  currentStepIndex: number;
}

export function WizardStepIndicator({ steps, currentStepIndex }: WizardStepIndicatorProps) {
  return (
    <div className="flex items-center gap-3">
      {steps.map((step, index) => {
        const isDone = index < currentStepIndex;
        const isCurrent = index === currentStepIndex;
        return (
          <div key={step} className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                  isDone && "bg-accent text-accent-foreground",
                  isCurrent && "bg-accent text-accent-foreground",
                  !isDone && !isCurrent && "bg-muted text-muted-foreground",
                )}
              >
                {isDone ? <Check className="h-3.5 w-3.5" /> : index + 1}
              </div>
              <span
                className={cn(
                  "text-sm font-medium",
                  isCurrent ? "text-foreground" : "text-muted-foreground",
                )}
              >
                {step}
              </span>
            </div>
            {index < steps.length - 1 && <div className="h-px w-10 bg-border" />}
          </div>
        );
      })}
    </div>
  );
}
