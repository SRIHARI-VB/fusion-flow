import { useState } from "react";
import { ArrowUpDown, MoreHorizontal, Plus, Search } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@fusion-flow/ui";

interface Transaction {
  id: string;
  customer: string;
  amount: string;
  status: "Completed" | "Pending" | "Failed";
  method: string;
  date: string;
}

const transactions: Transaction[] = [
  { id: "TX-1042", customer: "Priya Sharma", amount: "$1,240.00", status: "Completed", method: "Razorpay", date: "Sep 08, 2026" },
  { id: "TX-1041", customer: "Daniel Kim", amount: "$389.50", status: "Pending", method: "WhatsApp Pay", date: "Sep 08, 2026" },
  { id: "TX-1040", customer: "Amara Okafor", amount: "$76.00", status: "Completed", method: "Razorpay", date: "Sep 07, 2026" },
  { id: "TX-1039", customer: "Lucas Meyer", amount: "$212.20", status: "Failed", method: "Razorpay", date: "Sep 07, 2026" },
  { id: "TX-1038", customer: "Zainab Ali", amount: "$958.10", status: "Completed", method: "Razorpay", date: "Sep 06, 2026" },
];

const statusVariant: Record<Transaction["status"], "success" | "secondary" | "destructive"> = {
  Completed: "success",
  Pending: "secondary",
  Failed: "destructive",
};

export function TransactionsTable() {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const allSelected = selected.size === transactions.length;

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(transactions.map((t) => t.id)));
  }

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-4">
        <CardTitle>Recent Transactions</CardTitle>
        <div className="flex items-center gap-2">
          <div className="relative hidden sm:block">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input placeholder="Search transactions" className="h-9 w-56 pl-8 text-sm" />
          </div>
          <Button size="sm">
            <Plus className="h-4 w-4" /> Add
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <input
                  type="checkbox"
                  aria-label="Select all transactions"
                  checked={allSelected}
                  onChange={toggleAll}
                  className="h-4 w-4 rounded border-border accent-accent"
                />
              </TableHead>
              <TableHead>
                <span className="flex items-center gap-1">
                  Transaction <ArrowUpDown className="h-3 w-3" />
                </span>
              </TableHead>
              <TableHead>
                <span className="flex items-center gap-1">
                  Customer <ArrowUpDown className="h-3 w-3" />
                </span>
              </TableHead>
              <TableHead>
                <span className="flex items-center gap-1">
                  Amount <ArrowUpDown className="h-3 w-3" />
                </span>
              </TableHead>
              <TableHead>Method</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Date</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {transactions.map((tx) => (
              <TableRow key={tx.id}>
                <TableCell>
                  <input
                    type="checkbox"
                    aria-label={`Select ${tx.id}`}
                    checked={selected.has(tx.id)}
                    onChange={() => toggleOne(tx.id)}
                    className="h-4 w-4 rounded border-border accent-accent"
                  />
                </TableCell>
                <TableCell className="font-medium text-foreground">{tx.id}</TableCell>
                <TableCell>{tx.customer}</TableCell>
                <TableCell>{tx.amount}</TableCell>
                <TableCell>{tx.method}</TableCell>
                <TableCell>
                  <Badge variant={statusVariant[tx.status]}>{tx.status}</Badge>
                </TableCell>
                <TableCell className="text-muted-foreground">{tx.date}</TableCell>
                <TableCell>
                  <Button variant="ghost" size="icon" aria-label={`Actions for ${tx.id}`}>
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
