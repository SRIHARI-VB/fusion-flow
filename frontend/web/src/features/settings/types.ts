import type { MembershipRole } from "@fusion-flow/ts-types";

/** One row of `GET /api/v1/businesses/{id}/members`. */
export interface Member {
  id: string;
  email: string;
  role: MembershipRole;
  invited_at: string;
  accepted_at: string | null;
  /** Clinic-queue doctor designation - see `Membership.is_doctor`'s own
   * docstring for why it's separate from `role`. Owner/admin-editable via
   * `PATCH /api/v1/businesses/{id}/members/{membership_id}`. */
  is_doctor: boolean;
}
