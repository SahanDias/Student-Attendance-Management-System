import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Next.js's own dev-mode indicator renders bottom-left by default -- the
  // exact corner the bundled Lovable badge used to occupy, and easily
  // mistaken for it. No Lovable script or badge remains anywhere in the
  // codebase (already removed); this just turns off Next's own icon too.
  devIndicators: false,
};

export default nextConfig;
