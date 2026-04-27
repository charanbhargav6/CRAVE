import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  typescript: { ignoreBuildErrors: true },
  allowedDevOrigins: ["192.168.43.243", "localhost"],
  async redirects() {
    return [
      {
        source: "/",
        destination: "/backtest",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
