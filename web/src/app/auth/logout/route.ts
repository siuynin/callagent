import { type NextRequest, NextResponse } from "next/server";

import { discovery, oidcConfig } from "@/lib/oidc";
import { SESSION_COOKIE, type Session, unseal } from "@/lib/session";

// POST only: a cross-site link or image must not be able to sign people out.
export async function POST(request: NextRequest) {
  const { appOrigin } = oidcConfig();
  const session = await unseal<Session>(request.cookies.get(SESSION_COOKIE)?.value);
  let target = new URL("/dang-nhap", appOrigin);
  if (session && process.env.OIDC_ISSUER) {
    const doc = await discovery().catch(() => null);
    if (doc?.end_session_endpoint) {
      target = new URL(doc.end_session_endpoint);
      target.search = new URLSearchParams({
        id_token_hint: session.idToken,
        post_logout_redirect_uri: `${appOrigin}/dang-nhap`,
      }).toString();
    }
  }
  const res = NextResponse.redirect(target, 303);
  res.cookies.delete(SESSION_COOKIE);
  return res;
}
