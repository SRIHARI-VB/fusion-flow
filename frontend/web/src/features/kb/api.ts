import { apiClient } from "../../lib/api-client";
import type { KbArticle, KbArticleCreateInput, KbArticleUpdateInput } from "./types";

const BASE = "/api/v1/kb-articles";

export async function listArticles(): Promise<KbArticle[]> {
  const { data } = await apiClient.get<KbArticle[]>(BASE);
  return data;
}

export async function getArticle(id: string): Promise<KbArticle> {
  const { data } = await apiClient.get<KbArticle>(`${BASE}/${id}`);
  return data;
}

export async function createArticle(payload: KbArticleCreateInput): Promise<KbArticle> {
  const { data } = await apiClient.post<KbArticle>(BASE, payload);
  return data;
}

export async function updateArticle(id: string, payload: KbArticleUpdateInput): Promise<KbArticle> {
  const { data } = await apiClient.patch<KbArticle>(`${BASE}/${id}`, payload);
  return data;
}

export async function deleteArticle(id: string): Promise<void> {
  await apiClient.delete(`${BASE}/${id}`);
}
