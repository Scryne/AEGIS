import path from "node:path";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Standalone çıktı yalnızca Docker imajında (Linux) etkinleşir: Windows'ta Next'in
  // standalone symlink adımı Developer Mode olmadan EPERM verebilir. Yerel build bu
  // yüzden standart çıktı kullanır (NEXT_OUTPUT=standalone ile açılmadıkça).
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  outputFileTracingRoot: path.join(import.meta.dirname, "../.."),
};

export default nextConfig;
