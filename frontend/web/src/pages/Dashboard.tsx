import { CalendarDays, Download, DollarSign, ShoppingBag, Users, TrendingUp } from "lucide-react";
import { Button } from "@fusion-flow/ui";
import { KpiCard } from "../components/dashboard/KpiCard";
import { TrendChart } from "../components/dashboard/TrendChart";
import { TransactionsTable } from "../components/dashboard/TransactionsTable";
import { useAuthStore } from "../lib/auth-store";

const kpis = [
  { label: "Total Revenue", value: "$48,231", delta: "+12.4%", icon: DollarSign, sparkline: [4, 6, 5, 8, 7, 9, 10] },
  { label: "Orders", value: "1,204", delta: "+8.1%", icon: ShoppingBag, sparkline: [3, 4, 4, 5, 6, 5, 7] },
  { label: "New Customers", value: "312", delta: "+4.6%", icon: Users, sparkline: [2, 3, 3, 4, 3, 5, 6] },
  { label: "Conversion Rate", value: "3.8%", delta: "+1.2%", icon: TrendingUp, sparkline: [5, 5, 6, 6, 7, 6, 8] },
];

export function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const firstName = user?.email.split("@")[0] ?? "there";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Welcome back, {firstName}</h1>
          <p className="text-sm text-muted-foreground">Here's what's happening with your business today.</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            aria-label="Period"
            className="h-10 rounded-md border border-input bg-card px-3 text-sm text-foreground"
            defaultValue="weekly"
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
          <Button variant="outline">
            <CalendarDays className="h-4 w-4" />
            Sep 1 - Sep 8
          </Button>
          <Button>
            <Download className="h-4 w-4" />
            Export CSV
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map((kpi) => (
          <KpiCard key={kpi.label} {...kpi} />
        ))}
      </div>

      <TrendChart />

      <TransactionsTable />
    </div>
  );
}
