import "server-only";

import { cookies } from "next/headers";

// Encrypted, httpOnly session cookie holding the OIDC ID token the backend verifies (ADR 0008).
// AES-256-GCM with a key derived from SESSION_SECRET; tampering or a wrong secret makes it unreadable.

export const SESSION_COOKIE = "voiceos_session";
export const LOGIN_COOKIE = "voiceos_oidc";

export type Session = { idToken: string; exp: number; name?: string; email?: string };

export function oidcEnabled(): boolean {
  return !!process.env.OIDC_ISSUER;
}

async function key(): Promise<CryptoKey> {
  const secret = process.env.SESSION_SECRET ?? "";
  if (secret.length < 32) throw new Error("SESSION_SECRET must be at least 32 characters when OIDC is enabled");
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(secret));
  return crypto.subtle.importKey("raw", digest, "AES-GCM", false, ["encrypt", "decrypt"]);
}

const b64u = (buf: ArrayBuffer | Uint8Array) => Buffer.from(buf as ArrayBuffer).toString("base64url");

export async function seal(data: unknown): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await key(), new TextEncoder().encode(JSON.stringify(data)));
  return `${b64u(iv)}.${b64u(ct)}`;
}

export async function unseal<T>(value: string | undefined): Promise<T | null> {
  if (!value) return null;
  const [iv, ct] = value.split(".");
  if (!iv || !ct) return null;
  try {
    const pt = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: Buffer.from(iv, "base64url") },
      await key(),
      Buffer.from(ct, "base64url"),
    );
    return JSON.parse(new TextDecoder().decode(pt)) as T;
  } catch {
    return null;
  }
}

/** Current session, or null when missing, tampered or expired. Usable in Server Components and actions. */
export async function getSession(): Promise<Session | null> {
  const session = await unseal<Session>((await cookies()).get(SESSION_COOKIE)?.value);
  if (!session || session.exp * 1000 <= Date.now()) return null;
  return session;
}

/** Decode a JWT payload WITHOUT verifying it (the backend verifies); used for exp/nonce/name only. */
export function jwtPayload(token: string): Record<string, unknown> {
  const part = token.split(".")[1];
  return part ? JSON.parse(Buffer.from(part, "base64url").toString("utf8")) : {};
}
