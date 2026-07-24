import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  outputFileTracingIncludes: {
    "/api/query": ["./stock/**/*"],
    "/api/modules": ["./stock/**/*"],
  },
};

export default nextConfig;
