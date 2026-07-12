import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  logging: {
    fetches: {
      fullUrl: true,
    },
  },
  experimental: {
    allowedDevOrigins: ['10.140.255.63', 'localhost:3000'],
  },
};

export default nextConfig;