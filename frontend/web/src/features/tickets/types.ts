/** Mirrors `fusionflow.modules.tickets.schemas` on the backend. */
export type TicketStatus = "open" | "pending" | "resolved" | "closed";
export type TicketMessageAuthorType = "customer" | "agent" | "system" | "support_agent_ai";

export interface Ticket {
  id: string;
  customer_id: string | null;
  customer_name: string | null;
  subject: string;
  status: TicketStatus;
  priority: string;
  source_connector_instance_id: string | null;
  assigned_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface TicketMessage {
  id: string;
  ticket_id: string;
  author_type: TicketMessageAuthorType;
  body: string;
  attachments: unknown[];
  created_at: string;
}

export interface TicketCreateInput {
  customer_id?: string | null;
  subject: string;
  status?: TicketStatus;
  priority?: string;
  assigned_user_id?: string | null;
}

export interface TicketUpdateInput {
  subject?: string;
  status?: TicketStatus;
  priority?: string;
  assigned_user_id?: string | null;
}

export interface TicketMessageCreateInput {
  author_type: TicketMessageAuthorType;
  body: string;
  attachments?: unknown[];
}

/** `POST /{ticket_id}/messages`'s response - the message is always stored,
 * but reaching the customer over their original channel is a separate,
 * best-effort outbound call reported here so "saved" is never confused
 * with "delivered" (see `tickets.schemas.TicketMessageSendResult`). */
export interface TicketMessageSendResult {
  message: TicketMessage;
  dispatched: boolean;
  dispatch_error: string | null;
}
