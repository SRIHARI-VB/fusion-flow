import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { Card, CardContent } from "@fusion-flow/ui";
import { WizardStepIndicator } from "./WizardStepIndicator";

/**
 * The shared shell every predefined-automation (and, later, broadcast-
 * campaign) wizard is built from - a guided step-by-step form, explicitly
 * NOT the workflow canvas. Two-column layout mirrors the Profiterasoft
 * reference this feature was built against: the step's own form on the
 * left, a `sidebar` slot on the right for whatever mix of
 * `LivePreviewPanel`/`SummarySidebar`/`TipsCallout` the step wants to show
 * alongside it.
 */
interface WizardShellProps {
  title: string;
  description?: string;
  backTo?: string;
  backLabel?: string;
  steps?: string[];
  currentStepIndex?: number;
  sidebar?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}

export function WizardShell({
  title,
  description,
  backTo,
  backLabel = "Back",
  steps,
  currentStepIndex = 0,
  sidebar,
  children,
  footer,
}: WizardShellProps) {
  return (
    <div className="flex flex-col gap-6">
      {backTo && (
        <Link
          to={backTo}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          {backLabel}
        </Link>
      )}

      <div>
        <h1 className="text-2xl font-semibold text-foreground">{title}</h1>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>

      {steps && steps.length > 0 && (
        <WizardStepIndicator steps={steps} currentStepIndex={currentStepIndex} />
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card>
          <CardContent className="flex flex-col gap-4 pt-6">{children}</CardContent>
        </Card>
        {sidebar && <div className="flex flex-col gap-4">{sidebar}</div>}
      </div>

      {footer && <div className="flex justify-end gap-2">{footer}</div>}
    </div>
  );
}
