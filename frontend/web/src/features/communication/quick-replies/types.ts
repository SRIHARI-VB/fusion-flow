export interface QuickReply {
  id: string;
  title: string;
  body: string;
  created_at: string;
  updated_at: string;
}

export interface QuickReplyPayload {
  title: string;
  body: string;
}
