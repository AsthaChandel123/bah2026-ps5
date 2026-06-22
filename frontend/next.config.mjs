/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Emit a self-contained server bundle (.next/standalone) so the Docker
  // production image can run `node server.js` without node_modules. See
  // frontend/Dockerfile.
  output: "standalone",
  // deck.gl / maplibre ship ESM; transpile to be safe across versions.
  transpilePackages: [
    "@deck.gl/core",
    "@deck.gl/layers",
    "@deck.gl/aggregation-layers",
    "@deck.gl/geo-layers",
    "@deck.gl/mapbox",
    "maplibre-gl",
  ],
  webpack: (config) => {
    // uPlot ships an untranspiled ESM build; allow importing its CSS too.
    config.resolve.alias = {
      ...config.resolve.alias,
    };
    return config;
  },
};

export default nextConfig;
