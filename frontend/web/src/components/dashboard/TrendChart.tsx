import { useState } from "react";
import { MoreHorizontal, Info } from "lucide-react";
import { Button, Card, CardContent, CardHeader } from "@fusion-flow/ui";

interface WeekPoint {
  label: string;
  newUsers: number;
  existingUsers: number;
}

const data: WeekPoint[] = [
  { label: "Mon", newUsers: 32, existingUsers: 58 },
  { label: "Tue", newUsers: 41, existingUsers: 62 },
  { label: "Wed", newUsers: 28, existingUsers: 70 },
  { label: "Thu", newUsers: 55, existingUsers: 64 },
  { label: "Fri", newUsers: 47, existingUsers: 80 },
  { label: "Sat", newUsers: 63, existingUsers: 52 },
  { label: "Sun", newUsers: 38, existingUsers: 45 },
];

const periods = ["Weekly", "Monthly", "Yearly"] as const;

const max = Math.max(...data.map((d) => d.newUsers + d.existingUsers));

export function TrendChart() {
  const [period, setPeriod] = useState<(typeof periods)[number]>("Weekly");
  const [hovered, setHovered] = useState<number | null>(null);

  const total = data.reduce((sum, d) => sum + d.newUsers + d.existingUsers, 0);

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4 pb-2">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-foreground">Revenue Trend</h3>
            <Info className="h-3.5 w-3.5 text-muted-foreground" />
          </div>
          <p className="mt-1 text-2xl font-bold text-foreground">{total.toLocaleString()}</p>
        </div>
        <Button variant="ghost" size="icon" aria-label="More options">
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </CardHeader>

      <CardContent>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4 text-xs">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-accent" /> New user
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-accent-soft" /> Existing user
            </span>
          </div>
          <div className="flex rounded-md border border-border p-0.5">
            {periods.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPeriod(p)}
                className={
                  "rounded-sm px-3 py-1 text-xs font-medium transition-colors " +
                  (period === p ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:text-foreground")
                }
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        <div className="relative mt-6 flex h-56 items-end gap-3">
          {data.map((point, i) => {
            const newHeight = (point.newUsers / max) * 100;
            const existingHeight = (point.existingUsers / max) * 100;
            return (
              <div
                key={point.label}
                className="relative flex flex-1 flex-col items-center gap-2"
                onMouseEnter={() => setHovered(i)}
                onMouseLeave={() => setHovered(null)}
              >
                {hovered === i && (
                  <div className="absolute -top-16 z-10 rounded-md border border-border bg-card p-2 text-xs shadow-card">
                    <p className="font-medium text-foreground">{point.label}</p>
                    <p className="text-accent">New: {point.newUsers}</p>
                    <p className="text-muted-foreground">Existing: {point.existingUsers}</p>
                  </div>
                )}
                <div className="flex h-48 w-full flex-col justify-end gap-0.5">
                  <div className="w-full rounded-t-sm bg-accent" style={{ height: `${newHeight}%` }} />
                  <div className="w-full rounded-b-sm bg-accent-soft" style={{ height: `${existingHeight}%` }} />
                </div>
                <span className="text-xs text-muted-foreground">{point.label}</span>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
