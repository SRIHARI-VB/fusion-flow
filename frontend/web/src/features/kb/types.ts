/** Mirrors `fusionflow.modules.kb.schemas` on the backend. */
export type KbArticleStatus = "draft" | "published";

export interface KbArticle {
  id: string;
  title: string;
  body: string;
  tags: string[];
  status: KbArticleStatus;
  created_at: string;
  updated_at: string;
}

export interface KbArticleCreateInput {
  title: string;
  body: string;
  tags?: string[];
  status?: KbArticleStatus;
}

export type KbArticleUpdateInput = Partial<KbArticleCreateInput>;
