import type { LucideIcon } from "lucide-react";
import { ArrowUpRight, Info } from "lucide-react";
import { Card, CardContent } from "@fusion-flow/ui";

export interface KpiCardProps {
  label: string;
  value: string;
  delta: string;
  icon: LucideIcon;
  sparkline: number[];
}

export function KpiCard({ label, value, delta, icon: Icon, sparkline }: KpiCardProps) {
  const max = Math.max(...sparkline, 1);
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
            <p className="mt-2 text-2xl font-bold text-foreground">{value}</p>
          </div>
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-accent-soft text-accent">
            <Icon className="h-4 w-4" />
          </div>
        </div>

        <div className="mt-4 flex h-8 items-end gap-1">
          {sparkline.map((v, i) => (
            <div
              key={i}
              className="w-1.5 flex-1 rounded-sm bg-accent-soft"
              style={{ height: `${Math.max((v / max) * 100, 8)}%` }}
            />
          ))}
        </div>

        <div className="mt-3 flex items-center justify-between border-t border-border pt-3">
          <Info className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="flex items-center gap-0.5 text-xs font-medium text-success">
            <ArrowUpRight className="h-3.5 w-3.5" />
            {delta} last year
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
