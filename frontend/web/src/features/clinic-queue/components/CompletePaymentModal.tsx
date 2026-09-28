import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Input } from "@fusion-flow/ui";
import { transitionStage } from "../api";
import { PAYMENT_MODE_LABELS, type PatientVisit, type PaymentMode } from "../types";
import { Modal } from "./Modal";

const selectClass = "h-10 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground";
const PAYMENT_MODES = Object.keys(PAYMENT_MODE_LABELS) as PaymentMode[];

/** The receptionist's final "Complete" action on a Billing-column card -
 * not a drag target, a button on the card itself (per the build directive:
 * receptionist picks the payment mode here). */
export function CompletePaymentModal({ visit, onClose }: { visit: PatientVisit | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [paymentMode, setPaymentMode] = useState<PaymentMode>("cash");
  const [amount, setAmount] = useState("");

  useEffect(() => {
    setPaymentMode("cash");
    setAmount(visit?.amount_to_collect != null ? String(visit.amount_to_collect) : "");
  }, [visit?.id, visit?.amount_to_collect]);

  const mutation = useMutation({
    mutationFn: () =>
      transitionStage(visit!.id, {
        stage: "completed",
        payment_mode: paymentMode,
        amount_collected: amount.trim() ? Number(amount) : undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clinic-queue", "visits"] });
      queryClient.invalidateQueries({ queryKey: ["clinic-queue", "history"] });
      onClose();
    },
  });

  return (
    <Modal open={visit !== null} title={`Complete payment for ${visit?.customer_name ?? ""}`} onClose={onClose}>
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium text-foreground">Payment mode</label>
        <select
          className={selectClass}
          value={paymentMode}
          onChange={(e) => setPaymentMode(e.target.value as PaymentMode)}
          autoFocus
        >
          {PAYMENT_MODES.map((mode) => (
            <option key={mode} value={mode}>
              {PAYMENT_MODE_LABELS[mode]}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium text-foreground">Amount collected</label>
        <Input
          type="number"
          min="0"
          step="0.01"
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="0.00"
        />
      </div>

      {mutation.isError && <p className="text-sm text-destructive">Could not complete payment. Please try again.</p>}

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose} disabled={mutation.isPending}>
          Cancel
        </Button>
        <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          {mutation.isPending ? "Saving..." : "Complete"}
        </Button>
      </div>
    </Modal>
  );
}
