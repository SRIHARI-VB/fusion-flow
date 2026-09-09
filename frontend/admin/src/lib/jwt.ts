import type { DecodedAccessToken } from "@fusion-flow/ts-types";

/** Minimal base64url JWT payload decode — no signature verification (see frontend/web equivalent). */
export function decodeAccessToken(token: string): DecodedAccessToken {
  const payload = token.split(".")[1];
  if (!payload) throw new Error("Malformed access token");
  const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
  const json = decodeURIComponent(
    atob(base64)
      .split("")
      .map((c) => "%" + c.charCodeAt(0).toString(16).padStart(2, "0"))
      .join(""),
  );
  return JSON.parse(json) as DecodedAccessToken;
}
