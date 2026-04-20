import type { NextConfig } from "next";

const allowedDevOrigins = (
  process.env.NEXT_ALLOWED_DEV_ORIGINS ?? "localhost,127.0.0.1,192.168.1.145"
)
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  allowedDevOrigins,
};

export default nextConfig;
