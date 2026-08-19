/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Workspace packages ship as TS source; Next transpiles them.
  transpilePackages: ["@stackgraph/design-system", "@stackgraph/shared", "@stackgraph/graph-ui"],
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
