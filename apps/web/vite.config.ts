import path from "node:path";
import * as dotenv from "dotenv";
import { reactRouter } from "@react-router/dev/vite";
import { defineConfig } from "vite";
import type { ProxyOptions } from "vite";
import tsconfigPaths from "vite-tsconfig-paths";

dotenv.config({ path: path.resolve(__dirname, ".env") });
// Optional override file (e.g. a same-origin production build served behind a proxy)
if (process.env.PLANE_WEB_ENV_OVERRIDE) {
  dotenv.config({ path: path.resolve(__dirname, process.env.PLANE_WEB_ENV_OVERRIDE), override: true });
}

// Expose only vars starting with VITE_
const viteEnv = Object.keys(process.env)
  .filter((k) => k.startsWith("VITE_"))
  .reduce<Record<string, string>>((a, k) => {
    a[k] = process.env[k] ?? "";
    return a;
  }, {});

// Opt-in same-origin dev server (PLANE_WEB_DEV_PROXY=1, set by scripts/local/dev-up.ps1): the client calls relative
// URLs and the dev server proxies them, so development also works when opened via a LAN/VPN host name. Targets:
// VITE_API_BASE_URL, VITE_LIVE_BASE_URL and PLANE_WEB_UPLOADS_PROXY_TARGET (MinIO: the API presigns
// <browser origin>/uploads/... URLs, so the Host header is kept for the signature to verify). Unset: upstream behaviour.
const isDevProxy = (command: string) => command === "serve" && process.env.PLANE_WEB_DEV_PROXY === "1";

const getDevProxy = (): Record<string, ProxyOptions> => {
  const { VITE_API_BASE_URL: apiTarget, VITE_LIVE_BASE_URL: liveTarget } = process.env;
  const uploadsTarget = process.env.PLANE_WEB_UPLOADS_PROXY_TARGET;
  const proxy: Record<string, ProxyOptions> = {};
  if (apiTarget)
    for (const prefix of ["/api", "/auth", "/static"]) proxy[prefix] = { target: apiTarget, changeOrigin: false };
  if (uploadsTarget) proxy["/uploads"] = { target: uploadsTarget, changeOrigin: false };
  if (liveTarget) proxy["/live"] = { target: liveTarget, changeOrigin: true, ws: true };
  return proxy;
};

const devProxyClientEnv = {
  VITE_API_BASE_URL: "",
  VITE_WEB_BASE_URL: "",
  VITE_LIVE_BASE_URL: "",
  VITE_LIVE_BASE_PATH: process.env.VITE_LIVE_BASE_PATH || "/live",
};

export default defineConfig(({ command }) => ({
  define: {
    "process.env": JSON.stringify(isDevProxy(command) ? { ...viteEnv, ...devProxyClientEnv } : viteEnv),
  },
  build: {
    assetsInlineLimit: 0,
  },
  plugins: [reactRouter(), tsconfigPaths({ projects: [path.resolve(__dirname, "tsconfig.json")] })],
  resolve: {
    alias: {
      // Next.js compatibility shims used within web
      "next/link": path.resolve(__dirname, "app/compat/next/link.tsx"),
      "next/navigation": path.resolve(__dirname, "app/compat/next/navigation.ts"),
      "next/script": path.resolve(__dirname, "app/compat/next/script.tsx"),
    },
    dedupe: ["react", "react-dom"],
  },
  server: {
    host: "127.0.0.1",
    ...(isDevProxy(command) ? { proxy: getDevProxy() } : {}),
  },
  // No SSR-specific overrides needed; alias resolves to ESM build
}));
