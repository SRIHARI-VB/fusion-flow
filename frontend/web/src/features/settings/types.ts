import type { MembershipRole } from "@fusion-flow/ts-types";

/** One row of `GET /api/v1/businesses/{id}/members` — read-only for phase 1. */
export interface Member {
  email: string;
  role: MembershipRole;
  invited_at: string;
  accepted_at: string | null;
}
