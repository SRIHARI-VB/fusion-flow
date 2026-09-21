import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type { AxiosError } from "axios";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Textarea } from "@fusion-flow/ui";
import { WizardShell, OptionPickerCard, SummarySidebar, TipsCallout } from "../../wizard";
import { useConnectorInstances } from "../../../connectors/hooks";
import { useCreateWhatsAppAutomation, useUpdateWhatsAppAutomation, useWhatsAppAutomations } from "../hooks";
import type { WhatsAppAutomationMatchingMethod } from "../api";

const STEPS = ["Trigger", "Service Details"];

const MATCHING_METHOD_OPTIONS: Array<{
  value: WhatsAppAutomationMatchingMethod;
  title: string;
  description: string;
}> = [
  { value: "exact", title: "Exact Match", description: "Keyword must match exactly" },
  { value: "contains", title: "Contains", description: "Message must contain the keyword" },
  { value: "starts_with", title: "Starts With", description: "Message must start with keyword" },
  { value: "ends_with", title: "Ends With", description: "Message must end with keyword" },
];

/**
 * `/communication/whatsapp/automations/new` (create) and
 * `/communication/whatsapp/automations/:id/edit` (edit) - the
 * "Appointment Booking" predefined-automation wizard. This automation
 * never books a real calendar slot: it auto-acknowledges the customer and
 * raises a support ticket for staff to confirm the actual time (see the
 * `TipsCallout` below), which is why there's no date/time step here.
 */
export function WhatsAppAutomationWizardPage() {
  const { id } = useParams<{ id: string }>();
  const isEditing = Boolean(id);
  const navigate = useNavigate();

  const { data: instances, isLoading: instancesLoading } = useConnectorInstances();
  const { data: automations, isLoading: automationsLoading } = useWhatsAppAutomations();
  const createMutation = useCreateWhatsAppAutomation();
  const updateMutation = useUpdateWhatsAppAutomation();

  const whatsappInstance = (instances ?? []).find(
    (instance) => instance.connector_type_key === "whatsapp" && instance.state === "connected",
  );
  const existing = isEditing ? (automations ?? []).find((automation) => automation.id === id) : undefined;

  const [stepIndex, setStepIndex] = useState(0);
  const [keywordsInput, setKeywordsInput] = useState("");
  const [matchingMethod, setMatchingMethod] = useState<WhatsAppAutomationMatchingMethod>("contains");
  const [serviceName, setServiceName] = useState("");
  const [durationMinutes, setDurationMinutes] = useState("");
  const [confirmationMessage, setConfirmationMessage] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  // Populate the form from the existing automation once (edit mode only) -
  // `automations` arrives async off the list endpoint (there's no
  // single-automation GET), so this can't be a plain `useState` initializer.
  const initializedRef = useRef(false);
  useEffect(() => {
    if (existing && !initializedRef.current) {
      setKeywordsInput(existing.config.trigger_keywords.join(", "));
      setMatchingMethod(existing.config.matching_method);
      setServiceName(existing.config.service_name);
      setDurationMinutes(String(existing.config.duration_minutes));
      setConfirmationMessage(existing.config.confirmation_message ?? "");
      initializedRef.current = true;
    }
  }, [existing]);

  const triggerKeywords = keywordsInput
    .split(",")
    .map((keyword) => keyword.trim())
    .filter(Boolean);

  const mutation = isEditing ? updateMutation : createMutation;
  const mutationError = mutation.error as AxiosError<{ detail?: string }> | null;

  if (instancesLoading || (isEditing && automationsLoading)) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  if (isEditing && !existing) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Automation not found</CardTitle>
          <CardDescription>This automation doesn't exist, or belongs to a different business.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  if (!whatsappInstance) {
    return (
      <Card>
        <CardHeader className="items-center text-center">
          <CardTitle>Connect WhatsApp first</CardTitle>
          <CardDescription>
            You need a connected WhatsApp number before you can set up an appointment booking automation.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex justify-center">
          <Link to="/connectors/whatsapp/connect">
            <Button>Connect WhatsApp</Button>
          </Link>
        </CardContent>
      </Card>
    );
  }

  function goNext() {
    if (stepIndex === 0 && triggerKeywords.length === 0) {
      setValidationError("Add at least one trigger keyword before continuing.");
      return;
    }
    setValidationError(null);
    setStepIndex((index) => Math.min(index + 1, STEPS.length - 1));
  }

  function goBack() {
    setValidationError(null);
    setStepIndex((index) => Math.max(index - 1, 0));
  }

  function handleSubmit() {
    if (!whatsappInstance) return;
    if (triggerKeywords.length === 0) {
      setValidationError("Add at least one trigger keyword before continuing.");
      setStepIndex(0);
      return;
    }
    if (!serviceName.trim()) {
      setValidationError("Service name is required.");
      return;
    }
    const duration = Number(durationMinutes);
    if (!Number.isFinite(duration) || duration <= 0) {
      setValidationError("Duration must be a number greater than 0.");
      return;
    }
    setValidationError(null);

    const config = {
      trigger_keywords: triggerKeywords,
      matching_method: matchingMethod,
      service_name: serviceName.trim(),
      duration_minutes: duration,
      confirmation_message: confirmationMessage.trim() ? confirmationMessage.trim() : null,
    };

    if (isEditing && id) {
      updateMutation.mutate(
        { id, config },
        { onSuccess: () => navigate("/communication/whatsapp/automations") },
      );
    } else {
      createMutation.mutate(
        {
          connector_instance_id: whatsappInstance.id,
          automation_type: "whatsapp.appointment_booking",
          name: serviceName.trim(),
          config,
        },
        { onSuccess: () => navigate("/communication/whatsapp/automations") },
      );
    }
  }

  const isLastStep = stepIndex === STEPS.length - 1;

  return (
    <WizardShell
      title={isEditing ? "Edit Appointment Booking Automation" : "New Appointment Booking Automation"}
      description="Auto-acknowledge WhatsApp messages that ask to book an appointment, and raise a ticket for your team to confirm the real time."
      backTo="/communication/whatsapp/automations"
      backLabel="Back to automations"
      steps={STEPS}
      currentStepIndex={stepIndex}
      sidebar={
        <>
          <SummarySidebar
            rows={[
              { label: "Keywords", value: triggerKeywords.join(", ") },
              {
                label: "Matching Method",
                value: MATCHING_METHOD_OPTIONS.find((option) => option.value === matchingMethod)?.title ?? "",
              },
              { label: "Service", value: serviceName },
              { label: "Duration", value: durationMinutes ? `${durationMinutes} min` : "" },
            ]}
          />
          <TipsCallout
            tips={[
              "This auto-acknowledges the customer instantly and raises a ticket for your team to confirm the real time.",
              "Leave the confirmation message blank to use a sensible generated default.",
            ]}
          />
        </>
      }
      footer={
        <>
          {stepIndex > 0 && (
            <Button variant="outline" onClick={goBack}>
              Previous
            </Button>
          )}
          {!isLastStep && <Button onClick={goNext}>Next</Button>}
          {isLastStep && (
            <Button onClick={handleSubmit} disabled={mutation.isPending}>
              {mutation.isPending ? "Saving…" : isEditing ? "Save changes" : "Create automation"}
            </Button>
          )}
        </>
      }
    >
      {stepIndex === 0 && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="trigger_keywords" className="text-sm font-medium">
              Trigger keywords
            </label>
            <Input
              id="trigger_keywords"
              placeholder="book, appointment, schedule"
              value={keywordsInput}
              onChange={(event) => setKeywordsInput(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">Separate multiple keywords with commas</p>
          </div>

          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium">Matching method</span>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {MATCHING_METHOD_OPTIONS.map((option) => (
                <OptionPickerCard
                  key={option.value}
                  title={option.title}
                  description={option.description}
                  selected={matchingMethod === option.value}
                  onSelect={() => setMatchingMethod(option.value)}
                />
              ))}
            </div>
          </div>
        </div>
      )}

      {stepIndex === 1 && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="service_name" className="text-sm font-medium">
              Service name
            </label>
            <Input
              id="service_name"
              placeholder="Consultation"
              value={serviceName}
              onChange={(event) => setServiceName(event.target.value)}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="duration_minutes" className="text-sm font-medium">
              Duration (minutes)
            </label>
            <Input
              id="duration_minutes"
              type="number"
              min={1}
              placeholder="30"
              value={durationMinutes}
              onChange={(event) => setDurationMinutes(event.target.value)}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="confirmation_message" className="text-sm font-medium">
              Confirmation message <span className="text-muted-foreground">(optional)</span>
            </label>
            <Textarea
              id="confirmation_message"
              placeholder={`Thanks for your interest in booking a ${serviceName || "{service name}"} (${
                durationMinutes || "{duration}"
              } min)! Our team will reach out shortly to confirm a time that works for you.`}
              value={confirmationMessage}
              onChange={(event) => setConfirmationMessage(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">Leave blank to use the generated default shown above.</p>
          </div>
        </div>
      )}

      {validationError && <p className="text-sm text-destructive">{validationError}</p>}
      {mutationError && (
        <p className="text-sm text-destructive">
          {mutationError.response?.data?.detail ?? "Could not save this automation."}
        </p>
      )}
    </WizardShell>
  );
}
