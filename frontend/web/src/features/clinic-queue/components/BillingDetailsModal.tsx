import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Input, Textarea } from "@fusion-flow/ui";
import { transitionStage } from "../api";
import type { PatientVisit } from "../types";
import { Modal } from "./Modal";

/** Opened when a doctor drags a patient card from their own column onto
 * Billing - the doctor's own two required inputs before billing can start. */
export function BillingDetailsModal({ visit, onClose }: { visit: PatientVisit | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState("");
  const [amount, setAmount] = useState("");

  useEffect(() => {
    setNotes("");
    setAmount("");
  }, [visit?.id]);

  const mutation = useMutation({
    mutationFn: () =>
      transitionStage(visit!.id, {
        stage: "billing",
        consultation_notes: notes.trim(),
        amount_to_collect: Number(amount),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clinic-queue", "visits"] });
      onClose();
    },
  });

  const amountValid = amount.trim().length > 0 && !Number.isNaN(Number(amount)) && Number(amount) >= 0;
  const canSubmit = notes.trim().length > 0 && amountValid && !mutation.isPending;

  return (
    <Modal
      open={visit !== null}
      title={`Send ${visit?.customer_name ?? ""} to billing`}
      description="Consultation notes stay visible to doctors only."
      onClose={onClose}
    >
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium text-foreground">Consultation notes</label>
        <Textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Diagnosis, treatment given, follow-up..."
          rows={4}
          autoFocus
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium text-foreground">Amount to collect</label>
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

      {mutation.isError && <p className="text-sm text-destructive">Could not save. Please try again.</p>}

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose} disabled={mutation.isPending}>
          Cancel
        </Button>
        <Button onClick={() => mutation.mutate()} disabled={!canSubmit}>
          {mutation.isPending ? "Saving..." : "Send to billing"}
        </Button>
      </div>
    </Modal>
  );
}
