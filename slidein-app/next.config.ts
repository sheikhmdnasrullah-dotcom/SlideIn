import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The client workspace is a console: no image optimisation target yet, and
  // keeping the bundle honest matters more than bytes here.
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
