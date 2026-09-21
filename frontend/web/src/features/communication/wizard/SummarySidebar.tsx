import { Card, CardContent, CardHeader, CardTitle } from "@fusion-flow/ui";

/** A running "Summary" panel that echoes back the wizard's current
 * answers as plain label/value rows - updates live as the form changes,
 * so the tenant always sees what they're about to save. */
interface SummaryRow {
  label: string;
  value: string;
}

interface SummarySidebarProps {
  rows: SummaryRow[];
}

export function SummarySidebar({ rows }: SummarySidebarProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Summary</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2 pt-0">
        {rows.map((row) => (
          <div key={row.label} className="flex flex-col gap-0.5">
            <span className="text-xs text-muted-foreground">{row.label}</span>
            <span className="text-sm font-medium text-foreground">{row.value || "—"}</span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
