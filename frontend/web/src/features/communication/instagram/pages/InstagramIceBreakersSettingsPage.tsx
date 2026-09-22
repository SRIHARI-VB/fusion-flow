import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AxiosError } from "axios";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from "@fusion-flow/ui";
import { useConnectorInstances } from "../../../connectors/hooks";
import { fetchIceBreakers, saveIceBreakers } from "../ice-breakers-api";

const MAX_QUESTIONS = 4;
const QUESTION_MAX_LENGTH = 80;

/**
 * `/communication/instagram/ice-breakers` - lets a tenant configure up
 * to 4 "Ice Breaker" welcome-menu questions Instagram shows as tappable
 * buttons to a customer opening a brand-new DM conversation with this
 * account for the first time. The tenant only ever sees/edits the
 * question text; `payload` is an opaque webhook-routing detail the
 * backend needs but the tenant doesn't, so it's derived automatically
 * (`ICE_BREAKER_<index>`) at save time.
 */
export function InstagramIceBreakersSettingsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: instances, isLoading: instancesLoading } = useConnectorInstances();
  const instagramInstance = (instances ?? []).find(
    (instance) => instance.connector_type_key === "instagram" && instance.state === "connected",
  );

  const { data: iceBreakers, isLoading: iceBreakersLoading } = useQuery({
    queryKey: ["instagram-ice-breakers", instagramInstance?.id],
    queryFn: () => fetchIceBreakers(instagramInstance!.id),
    enabled: !!instagramInstance,
  });

  const saveMutation = useMutation({
    mutationFn: (questions: string[]) =>
      saveIceBreakers(
        instagramInstance!.id,
        questions.map((question, index) => ({ question, payload: `ICE_BREAKER_${index}` })),
      ),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["instagram-ice-breakers", instagramInstance?.id] });
      queryClient.setQueryData(["instagram-ice-breakers", instagramInstance?.id], data);
    },
  });

  const [questions, setQuestions] = useState<string[]>([]);
  const [initialized, setInitialized] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => {
    if (initialized || !iceBreakers) return;
    setQuestions(iceBreakers.map((entry) => entry.question));
    setInitialized(true);
  }, [initialized, iceBreakers]);

  const mutationError = saveMutation.error as AxiosError<{ detail?: string }> | null;

  if (instancesLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  if (!instagramInstance) {
    return (
      <Card className="mx-auto max-w-lg">
        <CardHeader className="items-center text-center">
          <CardTitle>Connect Instagram first</CardTitle>
          <CardDescription>
            You need a connected Instagram account before you can set up a welcome menu.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex justify-center pb-6">
          <Button onClick={() => navigate("/connectors/instagram/connect")}>Connect Instagram</Button>
        </CardContent>
      </Card>
    );
  }

  function updateQuestion(index: number, value: string) {
    setQuestions((current) => current.map((question, i) => (i === index ? value : question)));
  }

  function addQuestion() {
    setQuestions((current) => (current.length >= MAX_QUESTIONS ? current : [...current, ""]));
  }

  function removeQuestion(index: number) {
    setQuestions((current) => current.filter((_, i) => i !== index));
  }

  function handleSave() {
    const trimmed = questions.map((question) => question.trim()).filter((question) => question.length > 0);
    if (trimmed.some((question) => question.length > QUESTION_MAX_LENGTH)) {
      setValidationError(`Each question must be ${QUESTION_MAX_LENGTH} characters or fewer.`);
      return;
    }
    setValidationError(null);
    saveMutation.mutate(trimmed);
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Welcome Menu (Ice Breakers)</h1>
        <p className="text-sm text-muted-foreground">
          Show up to 4 quick questions to anyone opening a new conversation with your Instagram account for the
          first time.
        </p>
      </div>

      <Card>
        <CardContent className="flex flex-col gap-4 pt-6">
          {iceBreakersLoading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (
            <>
              {questions.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  No ice breaker questions yet. Add one to get started.
                </p>
              )}

              {questions.map((question, index) => (
                <div key={index} className="flex items-center gap-2">
                  <Input
                    placeholder="e.g. What are your hours?"
                    value={question}
                    maxLength={QUESTION_MAX_LENGTH}
                    onChange={(event) => updateQuestion(index, event.target.value)}
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    aria-label="Remove question"
                    onClick={() => removeQuestion(index)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}

              {questions.length < MAX_QUESTIONS && (
                <Button variant="outline" onClick={addQuestion}>
                  <Plus className="h-4 w-4" />
                  Add Question
                </Button>
              )}

              {validationError && <p className="text-sm text-destructive">{validationError}</p>}
              {mutationError && (
                <p className="text-sm text-destructive">
                  {mutationError.response?.data?.detail ?? "Could not save the welcome menu."}
                </p>
              )}
              {saveMutation.isSuccess && !saveMutation.isPending && (
                <p className="text-sm text-success">Welcome menu saved.</p>
              )}

              <div className="flex justify-end">
                <Button onClick={handleSave} disabled={saveMutation.isPending}>
                  {saveMutation.isPending ? "Saving…" : "Save"}
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
