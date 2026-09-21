import { useEffect, useMemo, useRef, useState } from "react";
import type { ComponentType } from "react";
import type { IconBaseProps } from "react-icons";
import { SiFacebook, SiTelegram } from "react-icons/si";
import { MessageCircle, Search, Send, UserRound } from "lucide-react";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, cn } from "@fusion-flow/ui";
import { CONNECTOR_LOGO, CONNECTOR_LOGO_COLOR } from "../../../connectors/connector-logos";
import { formatRelativeTimestamp } from "../../../connectors/state-display";
import { useAssignAgent, useConversations, useMarkRead, useMessages, useSendMessage } from "../hooks";
import type { Conversation } from "../types";

/**
 * Brand marks for channels that don't have an entry in
 * `features/connectors/connector-logos.tsx::CONNECTOR_LOGO` yet (that map
 * only covers connectors with a dedicated connect flow so far - Telegram
 * and Facebook exist as seeded `connector_types` rows but no connect UI).
 * Kept local to this feature rather than added to that shared map, since
 * it's owned by `features/connectors` and out of this task's scope.
 */
const FALLBACK_CHANNEL_LOGO: Record<string, ComponentType<IconBaseProps>> = {
  telegram: SiTelegram,
  facebook: SiFacebook,
};

const FALLBACK_CHANNEL_LOGO_COLOR: Record<string, string> = {
  telegram: "#26A5E4",
  facebook: "#1877F2",
};

function getChannelIcon(channelKey: string): ComponentType<IconBaseProps> | undefined {
  return CONNECTOR_LOGO[channelKey] ?? FALLBACK_CHANNEL_LOGO[channelKey];
}

function getChannelColor(channelKey: string): string | undefined {
  return CONNECTOR_LOGO_COLOR[channelKey] ?? FALLBACK_CHANNEL_LOGO_COLOR[channelKey];
}

function ChannelIcon({ channelKey, className }: { channelKey: string; className?: string }) {
  const Icon = getChannelIcon(channelKey);
  const color = getChannelColor(channelKey);
  if (!Icon) {
    // Generic fallback for a channel with no brand mark at all (e.g. a
    // connector type added after this page shipped).
    return <MessageCircle className={className} />;
  }
  return <Icon className={className} color={color} />;
}

function channelLabel(channelKey: string): string {
  return channelKey.replace(/_/g, " ");
}

function pillClasses(active: boolean): string {
  return cn(
    "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium capitalize transition-colors",
    active
      ? "border-accent bg-accent-soft text-accent"
      : "border-border bg-card text-muted-foreground hover:bg-muted",
  );
}

/**
 * `/communication/inbox` - the cross-channel Unified Inbox: a
 * conversation list (left), the selected thread (middle), and a
 * contact/assignment panel (right). Backed by
 * `backend/src/fusionflow/modules/inbox` (`/api/v1/inbox/...`).
 *
 * Deliberately scoped to human-agent assignment only - no
 * chatbot-assignment or AI-call-assistant UI belongs here, that's a
 * separate scope decision made outside this feature.
 */
export function InboxPage() {
  const { data: conversations = [], isLoading: conversationsLoading } = useConversations();
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [channelFilter, setChannelFilter] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [composeText, setComposeText] = useState("");
  const [agentIdInput, setAgentIdInput] = useState("");

  const markReadMutation = useMarkRead();
  const sendMessageMutation = useSendMessage();
  const assignAgentMutation = useAssignAgent();

  const selectedConversation = conversations.find((c) => c.id === selectedConversationId) ?? null;
  const { data: messages = [], isLoading: messagesLoading } = useMessages(selectedConversationId ?? undefined);

  const channelKeys = useMemo(() => {
    const seen = new Set<string>();
    for (const conversation of conversations) {
      seen.add(conversation.connector_type_key);
    }
    return Array.from(seen).sort();
  }, [conversations]);

  const filteredConversations = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return conversations
      .filter((c) => channelFilter === null || c.connector_type_key === channelFilter)
      .filter((c) => {
        if (!query) return true;
        const haystack = `${c.display_name ?? ""} ${c.external_contact_id}`.toLowerCase();
        return haystack.includes(query);
      })
      .sort((a, b) => {
        const aTime = a.last_message_at ? new Date(a.last_message_at).getTime() : 0;
        const bTime = b.last_message_at ? new Date(b.last_message_at).getTime() : 0;
        return bTime - aTime;
      });
  }, [conversations, channelFilter, searchQuery]);

  // Keep the assign-agent input in sync with whichever conversation is
  // selected (and with its own re-fetched value after a successful assign).
  useEffect(() => {
    setAgentIdInput(selectedConversation?.assigned_agent_id ?? "");
  }, [selectedConversation?.id, selectedConversation?.assigned_agent_id]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length]);

  function handleSelectConversation(conversation: Conversation) {
    setSelectedConversationId(conversation.id);
    if (conversation.unread_count > 0) {
      markReadMutation.mutate(conversation.id);
    }
  }

  function handleSend() {
    const content = composeText.trim();
    if (!content || !selectedConversationId) return;
    sendMessageMutation.mutate(
      { conversationId: selectedConversationId, content },
      { onSuccess: () => setComposeText("") },
    );
  }

  function handleAssign() {
    if (!selectedConversation) return;
    const trimmed = agentIdInput.trim();
    assignAgentMutation.mutate({ conversationId: selectedConversation.id, agentId: trimmed || null });
  }

  function handleUnassign() {
    if (!selectedConversation) return;
    setAgentIdInput("");
    assignAgentMutation.mutate({ conversationId: selectedConversation.id, agentId: null });
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] min-h-[32rem] flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Unified Inbox</h1>
        <p className="text-sm text-muted-foreground">
          Every WhatsApp, Instagram, Telegram, and Facebook conversation in one place.
        </p>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[20rem_1fr_18rem] gap-4">
        {/* Left column: conversation list */}
        <Card className="flex min-h-0 flex-col overflow-hidden">
          <CardHeader className="gap-3 border-b border-border pb-3">
            <CardTitle>Conversations</CardTitle>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => setChannelFilter(null)} className={pillClasses(channelFilter === null)}>
                All
              </button>
              {channelKeys.map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setChannelFilter(key)}
                  className={pillClasses(channelFilter === key)}
                >
                  <ChannelIcon channelKey={key} className="h-3.5 w-3.5" />
                  {channelLabel(key)}
                </button>
              ))}
            </div>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Search conversations"
                className="pl-8"
              />
            </div>
          </CardHeader>
          <CardContent className="min-h-0 flex-1 overflow-y-auto p-0">
            {conversationsLoading ? (
              <p className="p-4 text-sm text-muted-foreground">Loading conversations...</p>
            ) : filteredConversations.length === 0 ? (
              <p className="p-4 text-sm text-muted-foreground">No conversations found.</p>
            ) : (
              <ul className="divide-y divide-border">
                {filteredConversations.map((conversation) => {
                  const isSelected = conversation.id === selectedConversationId;
                  return (
                    <li key={conversation.id}>
                      <button
                        type="button"
                        onClick={() => handleSelectConversation(conversation)}
                        className={cn(
                          "flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted",
                          isSelected && "bg-accent-soft",
                        )}
                      >
                        <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent">
                          <ChannelIcon channelKey={conversation.connector_type_key} className="h-4 w-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-2">
                            <p className="truncate text-sm font-medium text-foreground">
                              {conversation.display_name ?? conversation.external_contact_id}
                            </p>
                            <span className="flex-shrink-0 text-xs text-muted-foreground">
                              {formatRelativeTimestamp(conversation.last_message_at)}
                            </span>
                          </div>
                          <div className="mt-0.5 flex items-center justify-between gap-2">
                            <p className="truncate text-xs text-muted-foreground">{conversation.external_contact_id}</p>
                            {conversation.unread_count > 0 && (
                              <Badge variant="default" className="flex-shrink-0">
                                {conversation.unread_count}
                              </Badge>
                            )}
                          </div>
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Middle column: thread */}
        <Card className="flex min-h-0 flex-col overflow-hidden">
          {selectedConversation ? (
            <>
              <CardHeader className="flex-row items-center justify-between gap-3 border-b border-border pb-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-accent-soft text-accent">
                    <ChannelIcon channelKey={selectedConversation.connector_type_key} className="h-4 w-4" />
                  </div>
                  <div>
                    <CardTitle>{selectedConversation.display_name ?? selectedConversation.external_contact_id}</CardTitle>
                    <p className="text-xs text-muted-foreground">{selectedConversation.external_contact_id}</p>
                  </div>
                </div>
                <Badge variant="outline" className="capitalize">
                  {channelLabel(selectedConversation.connector_type_key)}
                </Badge>
              </CardHeader>

              <CardContent className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto py-4">
                {messagesLoading ? (
                  <p className="text-sm text-muted-foreground">Loading messages...</p>
                ) : messages.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No messages yet.</p>
                ) : (
                  messages.map((message) => {
                    const isOutbound = message.direction === "outbound";
                    return (
                      <div key={message.id} className={cn("flex", isOutbound ? "justify-end" : "justify-start")}>
                        <div
                          className={cn(
                            "max-w-[75%] rounded-lg px-3 py-2 text-sm",
                            isOutbound ? "bg-accent text-accent-foreground" : "bg-muted text-foreground",
                          )}
                        >
                          <p className="whitespace-pre-wrap">{message.content}</p>
                          <p
                            className={cn(
                              "mt-1 text-[10px]",
                              isOutbound ? "text-accent-foreground/70" : "text-muted-foreground",
                            )}
                          >
                            {formatRelativeTimestamp(message.created_at)}
                          </p>
                        </div>
                      </div>
                    );
                  })
                )}
                <div ref={messagesEndRef} />
              </CardContent>

              <div className="flex items-center gap-2 border-t border-border p-3">
                <Input
                  value={composeText}
                  onChange={(event) => setComposeText(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      handleSend();
                    }
                  }}
                  placeholder="Type a message"
                  disabled={sendMessageMutation.isPending}
                />
                <Button onClick={handleSend} disabled={!composeText.trim() || sendMessageMutation.isPending}>
                  <Send className="h-4 w-4" />
                  Send
                </Button>
              </div>
            </>
          ) : (
            <CardContent className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
              Select a conversation
            </CardContent>
          )}
        </Card>

        {/* Right column: contact / assignment panel */}
        <Card className="flex min-h-0 flex-col overflow-hidden">
          <CardHeader className="border-b border-border pb-3">
            <CardTitle>Contact Overview</CardTitle>
          </CardHeader>
          <CardContent className="min-h-0 flex-1 overflow-y-auto">
            {selectedConversation ? (
              <div className="flex flex-col gap-5 text-sm">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Contact</p>
                  <p className="mt-1 font-medium text-foreground">
                    {selectedConversation.display_name ?? "Unnamed contact"}
                  </p>
                  <p className="text-xs text-muted-foreground">{selectedConversation.external_contact_id}</p>
                </div>

                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Channel</p>
                  <div className="mt-1 flex items-center gap-2">
                    <ChannelIcon channelKey={selectedConversation.connector_type_key} className="h-4 w-4" />
                    <span className="capitalize">{channelLabel(selectedConversation.connector_type_key)}</span>
                  </div>
                </div>

                <div className="flex flex-col gap-2">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Assigned agent</p>
                  {/*
                    No user-picker endpoint exists in this frontend yet: the
                    only existing "team members" data source
                    (`features/settings/api.ts::fetchMembers`, backed by
                    `GET /api/v1/businesses/{id}/members`) returns email/role/
                    invited_at/accepted_at only - no user id, so it can't
                    populate an `agent_id` dropdown for `POST .../assign`.
                    Falling back to a plain user-id text input per this
                    task's spec until a members-with-id endpoint exists.
                  */}
                  <Input
                    value={agentIdInput}
                    onChange={(event) => setAgentIdInput(event.target.value)}
                    placeholder="Agent user id"
                  />
                  <div className="flex gap-2">
                    <Button size="sm" onClick={handleAssign} disabled={assignAgentMutation.isPending}>
                      <UserRound className="h-3.5 w-3.5" />
                      Assign
                    </Button>
                    {selectedConversation.assigned_agent_id && (
                      <Button size="sm" variant="outline" onClick={handleUnassign} disabled={assignAgentMutation.isPending}>
                        Unassign
                      </Button>
                    )}
                  </div>
                  {selectedConversation.assigned_agent_id && (
                    <p className="text-xs text-muted-foreground">
                      Currently assigned to user {selectedConversation.assigned_agent_id}
                    </p>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Select a conversation to see contact details.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
