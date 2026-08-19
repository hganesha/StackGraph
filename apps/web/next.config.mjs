/** @type {import('next').NextConfig} */
const isProd = process.env.NODE_ENV === "production";

// The live API origin must be reachable by the browser (connect-src). Fixtures need nothing.
const apiOrigin = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8080";

// Strict, self-contained CSP (plan §8.3): no third-party hosts; fonts/scripts/styles are self-hosted.
// Applied in production only — dev needs 'unsafe-eval'/websocket for HMR and tooling.
const csp = [
  "default-src 'self'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  "object-src 'none'",
  "img-src 'self' data:",
  "font-src 'self'",
  // Next injects inline styles; 'unsafe-inline' is required for styled/CSS-in-JS runtime.
  "style-src 'self' 'unsafe-inline'",
  "script-src 'self'",
  `connect-src 'self' ${apiOrigin}`,
].join("; ");

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), browsing-topics=()" },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  ...(isProd ? [{ key: "Content-Security-Policy", value: csp }] : []),
];

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Workspace packages ship as TS source; Next transpiles them.
  transpilePackages: ["@stackgraph/design-system", "@stackgraph/shared", "@stackgraph/graph-ui"],
  eslint: { ignoreDuringBuilds: true },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
