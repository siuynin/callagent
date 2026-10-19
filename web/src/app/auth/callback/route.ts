import { type NextRequest, NextResponse } from "next/server";

import { discovery, oidcConfig } from "@/lib/oidc";
import { jwtPayload, LOGIN_COOKIE, SESSION_COOKIE, seal, type Session, unseal } from "@/lib/session";

type Pending = { state: string; nonce: string; verifier: string; returnTo: string };

function fail(request: NextRequest, reason: string) {
  const res = NextResponse.redirect(new URL(`/chua-duoc-moi?reason=${encodeURIComponent(reason)}`, request.url));
  res.cookies.delete({ name: LOGIN_COOKIE, path: "/auth" });
  return res;
}

export async function GET(request: NextRequest) {
  const { clientId, clientSecret, appOrigin } = oidcConfig();
  const params = request.nextUrl.searchParams;
  const pending = await unseal<Pending>(request.cookies.get(LOGIN_COOKIE)?.value);
  if (params.get("error")) return fail(request, "PROVIDER_ERROR");
  // state must round-trip unchanged: protects against login CSRF / injected codes
  if (!pending || !params.get("code") || params.get("state") !== pending.state) return fail(request, "STATE_MISMATCH");

  const doc = await discovery();
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code: params.get("code")!,
    redirect_uri: `${appOrigin}/auth/callback`,
    client_id: clientId,
    code_verifier: pending.verifier,
  });
  if (clientSecret) body.set("client_secret", clientSecret);
  const tokenRes = await fetch(doc.token_endpoint, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
    cache: "no-store",
  });
  if (!tokenRes.ok) return fail(request, "TOKEN_EXCHANGE");
  const idToken = ((await tokenRes.json()) as { id_token?: string }).id_token;
  if (!idToken) return fail(request, "NO_ID_TOKEN");
  const claims = jwtPayload(idToken);
  if (claims.nonce !== pending.nonce) return fail(request, "NONCE_MISMATCH");

  // the backend verifies the signature and membership; only then is a session created
  const me = await fetch(`${process.env.API_ORIGIN ?? "http://127.0.0.1:8000"}/api/v1/me`, {
    headers: { authorization: `Bearer ${idToken}` },
    cache: "no-store",
  });
  if (!me.ok) {
    const code = ((await me.json().catch(() => null)) as { error?: { code?: string } } | null)?.error?.code;
    return fail(request, code ?? `HTTP_${me.status}`);
  }
  const session: Session = {
    idToken,
    exp: Number(claims.exp),
    name: typeof claims.name === "string" ? claims.name : undefined,
    email: typeof claims.email === "string" ? claims.email : undefined,
  };
  const res = NextResponse.redirect(new URL(pending.returnTo || "/", appOrigin));
  res.cookies.delete({ name: LOGIN_COOKIE, path: "/auth" });
  res.cookies.set(SESSION_COOKIE, await seal(session), {
    httpOnly: true,
    sameSite: "lax",
    secure: appOrigin.startsWith("https://"),
    path: "/",
    maxAge: Math.max(0, session.exp - Math.floor(Date.now() / 1000)),
  });
  return res;
}
