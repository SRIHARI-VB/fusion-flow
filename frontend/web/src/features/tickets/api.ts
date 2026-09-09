import { apiClient } from "../../lib/api-client";
import type {
  Ticket,
  TicketCreateInput,
  TicketMessage,
  TicketMessageCreateInput,
  TicketUpdateInput,
} from "./types";

const BASE = "/api/v1/tickets";

export async function listTickets(): Promise<Ticket[]> {
  const { data } = await apiClient.get<Ticket[]>(BASE);
  return data;
}

export async function getTicket(id: string): Promise<Ticket> {
  const { data } = await apiClient.get<Ticket>(`${BASE}/${id}`);
  return data;
}

export async function createTicket(payload: TicketCreateInput): Promise<Ticket> {
  const { data } = await apiClient.post<Ticket>(BASE, payload);
  return data;
}

export async function updateTicket(id: string, payload: TicketUpdateInput): Promise<Ticket> {
  const { data } = await apiClient.patch<Ticket>(`${BASE}/${id}`, payload);
  return data;
}

export async function listMessages(ticketId: string): Promise<TicketMessage[]> {
  const { data } = await apiClient.get<TicketMessage[]>(`${BASE}/${ticketId}/messages`);
  return data;
}

export async function addMessage(
  ticketId: string,
  payload: TicketMessageCreateInput,
): Promise<TicketMessage> {
  const { data } = await apiClient.post<TicketMessage>(`${BASE}/${ticketId}/messages`, payload);
  return data;
}
