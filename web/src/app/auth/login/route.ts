import { type NextRequest, NextResponse } from "next/server";

import { discovery, oidcConfig, pkceChallenge, randomToken, safeReturnTo } from "@/lib/oidc";
import { LOGIN_COOKIE, oidcEnabled, seal } from "@/lib/session";

// Authorization code + PKCE (S256). state/nonce/verifier live in a short-lived encrypted cookie.
export async function GET(request: NextRequest) {
  if (!oidcEnabled()) return NextResponse.redirect(new URL("/", request.url));
  const { clientId, appOrigin } = oidcConfig();
  const returnTo = safeReturnTo(request.nextUrl.searchParams.get("returnTo"));
  const state = randomToken();
  const nonce = randomToken();
  const verifier = randomToken(48);
  const doc = await discovery();
  const url = new URL(doc.authorization_endpoint);
  url.search = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: `${appOrigin}/auth/callback`,
    scope: "openid email profile",
    state,
    nonce,
    code_challenge: await pkceChallenge(verifier),
    code_challenge_method: "S256",
  }).toString();
  const res = NextResponse.redirect(url);
  res.cookies.set(LOGIN_COOKIE, await seal({ state, nonce, verifier, returnTo }), {
    httpOnly: true,
    sameSite: "lax",
    secure: appOrigin.startsWith("https://"),
    path: "/auth",
    maxAge: 600,
  });
  return res;
}
