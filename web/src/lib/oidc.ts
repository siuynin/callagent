import "server-only";

type Discovery = {
  authorization_endpoint: string;
  token_endpoint: string;
  end_session_endpoint?: string;
};

let cached: { issuer: string; doc: Discovery; at: number } | null = null;

export function oidcConfig() {
  return {
    issuer: process.env.OIDC_ISSUER ?? "",
    clientId: process.env.OIDC_CLIENT_ID ?? "",
    clientSecret: process.env.OIDC_CLIENT_SECRET ?? "",
    appOrigin: process.env.APP_ORIGIN ?? "http://localhost:3000",
  };
}

export async function discovery(): Promise<Discovery> {
  const { issuer } = oidcConfig();
  if (cached && cached.issuer === issuer && Date.now() - cached.at < 3600_000) return cached.doc;
  const res = await fetch(`${issuer.replace(/\/$/, "")}/.well-known/openid-configuration`, { cache: "no-store" });
  if (!res.ok) throw new Error(`OIDC discovery failed: ${res.status}`);
  const doc = (await res.json()) as Discovery;
  cached = { issuer, doc, at: Date.now() };
  return doc;
}

export function randomToken(bytes = 32): string {
  return Buffer.from(crypto.getRandomValues(new Uint8Array(bytes))).toString("base64url");
}

export async function pkceChallenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return Buffer.from(digest).toString("base64url");
}

/** Only same-site relative paths; anything else (//evil, https://…) falls back to "/" (open redirect guard). */
export function safeReturnTo(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return "/";
  return value;
}
