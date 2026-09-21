/**
 * Hand-written types mirroring the backend's Unified Inbox DTOs
 * (`backend/src/fusionflow/modules/inbox/schemas.py`). Kept local to this
 * feature rather than added to `@fusion-flow/ts-types` - same reasoning as
 * `features/connectors/types.ts`'s module docstring: that package is
 * shared across `web`+`admin` and owned outside this feature's boundary
 * for this wave.
 */

export interface Conversation {
  id: string;
  connector_instance_id: string;
  connector_type_key: string;
  external_contact_id: string;
  display_name: string | null;
  assigned_agent_id: string | null;
  last_message_at: string | null;
  unread_count: number;
  created_at: string;
  updated_at: string;
}

export type MessageDirection = "inbound" | "outbound";
export type MessageSenderType = "customer" | "agent";

export interface Message {
  id: string;
  conversation_id: string;
  direction: MessageDirection;
  sender_type: MessageSenderType;
  content: string;
  external_message_id: string | null;
  created_at: string;
  read_at: string | null;
}
