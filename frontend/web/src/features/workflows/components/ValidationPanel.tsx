import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { Badge, Card, CardContent, CardHeader, CardTitle } from "@fusion-flow/ui";
import { VALIDATION_RULES, type ValidationIssue } from "../types";

/**
 * Lists all 5 publish-time validation checks (plan's "Workflow Engine"
 * section) with pass/fail state, plus every collected issue underneath —
 * `validate_for_publish` on the backend never stops at the first failure,
 * so neither does this panel.
 */

interface ValidationPanelProps {
  issues: ValidationIssue[] | null;
  onClose: () => void;
}

export function ValidationPanel({ issues, onClose }: ValidationPanelProps) {
  const byRule = new Map<string, ValidationIssue[]>();
  for (const issue of issues ?? []) {
    byRule.set(issue.rule, [...(byRule.get(issue.rule) ?? []), issue]);
  }

  return (
    <div className="absolute bottom-4 right-[17rem] z-10 w-96 max-h-[60vh] overflow-y-auto">
      <Card className="shadow-lg">
        <CardHeader className="flex-row items-center justify-between gap-2 py-3">
          <CardTitle className="text-sm">Publish validation</CardTitle>
          <button
            type="button"
            className="text-xs text-muted-foreground hover:text-foreground"
            onClick={onClose}
          >
            Close
          </button>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 pt-0">
          {issues === null && (
            <p className="text-xs text-muted-foreground">Run publish to see validation results.</p>
          )}

          {issues !== null &&
            VALIDATION_RULES.map(({ rule, label }) => {
              const ruleIssues = byRule.get(rule) ?? [];
              const hasError = ruleIssues.some((i) => i.severity === "error");
              const hasWarning = ruleIssues.some((i) => i.severity === "warning");

              return (
                <div key={rule} className="flex flex-col gap-1 border-b border-border pb-2 last:border-0">
                  <div className="flex items-center gap-2">
                    {hasError ? (
                      <XCircle className="h-4 w-4 text-destructive" />
                    ) : hasWarning ? (
                      <AlertTriangle className="h-4 w-4 text-accent" />
                    ) : (
                      <CheckCircle2 className="h-4 w-4 text-success" />
                    )}
                    <span className="text-sm font-medium text-foreground">{label}</span>
                    {hasError && <Badge variant="destructive">Failed</Badge>}
                    {!hasError && hasWarning && <Badge variant="default">Warning</Badge>}
                    {!hasError && !hasWarning && <Badge variant="success">Passed</Badge>}
                  </div>
                  {ruleIssues.map((issue, index) => (
                    <p key={index} className="pl-6 text-xs text-muted-foreground">
                      {issue.node_id && <span className="font-mono">[{issue.node_id}] </span>}
                      {issue.message}
                    </p>
                  ))}
                </div>
              );
            })}
        </CardContent>
      </Card>
    </div>
  );
}
