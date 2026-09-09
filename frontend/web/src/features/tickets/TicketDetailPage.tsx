import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Send } from "lucide-react";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, cn } from "@fusion-flow/ui";
import { addMessage, getTicket, listMessages, updateTicket } from "./api";
import type { TicketMessageAuthorType, TicketStatus } from "./types";

const statuses: TicketStatus[] = ["open", "pending", "resolved", "closed"];

const authorLabel: Record<TicketMessageAuthorType, string> = {
  customer: "Customer",
  agent: "Agent",
  system: "System",
  support_agent_ai: "AI Agent",
};

export function TicketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [reply, setReply] = useState("");
  const [authorType, setAuthorType] = useState<TicketMessageAuthorType>("agent");

  const { data: ticket, isLoading: ticketLoading } = useQuery({
    queryKey: ["tickets", id],
    queryFn: () => getTicket(id as string),
    enabled: !!id,
  });

  const { data: messages = [], isLoading: messagesLoading } = useQuery({
    queryKey: ["tickets", id, "messages"],
    queryFn: () => listMessages(id as string),
    enabled: !!id,
  });

  const statusMutation = useMutation({
    mutationFn: (status: TicketStatus) => updateTicket(id as string, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tickets", id] });
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
    },
  });

  const replyMutation = useMutation({
    mutationFn: () => addMessage(id as string, { author_type: authorType, body: reply }),
    onSuccess: () => {
      setReply("");
      queryClient.invalidateQueries({ queryKey: ["tickets", id, "messages"] });
    },
  });

  if (ticketLoading || !ticket) {
    return <p className="text-sm text-muted-foreground">Loading...</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          to="/tickets"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to tickets
        </Link>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-foreground">{ticket.subject}</h1>
            <p className="text-sm text-muted-foreground">
              {ticket.customer_name ?? "No customer linked"} · Priority: {ticket.priority}
            </p>
          </div>
          <select
            className="h-10 rounded-md border border-input bg-card px-3 text-sm text-foreground"
            value={ticket.status}
            onChange={(event) => statusMutation.mutate(event.target.value as TicketStatus)}
          >
            {statuses.map((statusOption) => (
              <option key={statusOption} value={statusOption}>
                {statusOption}
              </option>
            ))}
          </select>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Conversation</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {messagesLoading && <p className="text-sm text-muted-foreground">Loading messages...</p>}
          {!messagesLoading && messages.length === 0 && (
            <p className="text-sm text-muted-foreground">No messages yet.</p>
          )}
          {messages.map((message) => {
            const fromCustomer = message.author_type === "customer";
            return (
              <div key={message.id} className={cn("flex", fromCustomer ? "justify-start" : "justify-end")}>
                <div
                  className={cn(
                    "max-w-[75%] rounded-lg px-4 py-2 text-sm",
                    fromCustomer ? "bg-muted text-foreground" : "bg-accent-soft text-foreground",
                  )}
                >
                  <div className="mb-1 flex items-center gap-2">
                    <Badge variant={fromCustomer ? "outline" : "default"}>
                      {authorLabel[message.author_type]}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {new Date(message.created_at).toLocaleString()}
                    </span>
                  </div>
                  <p className="whitespace-pre-wrap">{message.body}</p>
                </div>
              </div>
            );
          })}

          <form
            className="mt-4 flex flex-col gap-2 border-t border-border pt-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (reply.trim()) replyMutation.mutate();
            }}
          >
            <select
              className="h-9 w-fit rounded-md border border-input bg-card px-2 text-xs text-foreground"
              value={authorType}
              onChange={(event) => setAuthorType(event.target.value as TicketMessageAuthorType)}
            >
              <option value="agent">Reply as agent</option>
              <option value="system">Reply as system</option>
            </select>
            <textarea
              className="min-h-20 rounded-md border border-input bg-card p-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="Write a reply..."
              value={reply}
              onChange={(event) => setReply(event.target.value)}
            />
            <div>
              <Button type="submit" disabled={replyMutation.isPending || !reply.trim()}>
                <Send className="h-4 w-4" />
                {replyMutation.isPending ? "Sending..." : "Send reply"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
