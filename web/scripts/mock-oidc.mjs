// Local OIDC provider for development and tests ONLY (ADR 0008). Never point production at it.
//   node scripts/mock-oidc.mjs                  -> http://localhost:9400, signs in as MOCK_EMAIL
//   MOCK_EMAIL=staff-a@example.invalid MOCK_SUB=dev-staff node scripts/mock-oidc.mjs
// The authorize endpoint redirects straight back with a code (no login form); every token is for the
// configured user, with email_verified=true so invited accounts can bind on first sign-in.
import { OAuth2Server } from "oauth2-mock-server";

const port = Number(process.env.MOCK_OIDC_PORT ?? 9400);
const email = process.env.MOCK_EMAIL ?? "admin-a@example.invalid";
const sub = process.env.MOCK_SUB ?? `mock-${email}`;
const name = process.env.MOCK_NAME ?? email.split("@")[0];

const server = new OAuth2Server();
await server.issuer.keys.generate("RS256");
server.service.on("beforeTokenSigning", (token) => {
  Object.assign(token.payload, { sub, email, email_verified: true, name });
});
await server.start(port, "localhost");
console.log(`mock OIDC issuer ${server.issuer.url} signing in as ${email} (sub=${sub})`);
