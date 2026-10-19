import { type NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE, type Session, unseal } from "@/lib/session";

// Optimistic check only (ADR 0008): sends visitors without a live session to the sign-in page.
// Every API call is still authorised by the backend, which verifies the ID token itself.
export async function proxy(request: NextRequest) {
  if (!process.env.OIDC_ISSUER) return NextResponse.next();
  const session = await unseal<Session>(request.cookies.get(SESSION_COOKIE)?.value);
  if (session && session.exp * 1000 > Date.now()) return NextResponse.next();
  const login = new URL("/dang-nhap", request.url);
  login.searchParams.set("returnTo", request.nextUrl.pathname + request.nextUrl.search);
  return NextResponse.redirect(login);
}

export const config = {
  // everything except sign-in pages, auth routes, API proxy and static assets
  matcher: ["/((?!auth/|dang-nhap|chua-duoc-moi|api/|_next/|fonts/|favicon.ico).*)"],
};
