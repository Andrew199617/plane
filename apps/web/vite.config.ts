import path from "node:path";
import * as dotenv from "dotenv";
import { reactRouter } from "@react-router/dev/vite";
import { defineConfig } from "vite";
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

const apiProxyTarget = process.env.VITE_API_BASE_URL || "http://127.0.0.1:8300";
const liveProxyTarget = process.env.VITE_LIVE_BASE_URL || "http://127.0.0.1:3400";
// MinIO (host port of the local compose stack). The API runs with USE_MINIO=1, so presigned upload/download
// URLs point at <browser origin>/uploads/...; the proxies below keep the browser's Host header (like the
// production Caddy proxy) so the API signs for that host and MinIO can verify the signature.
const uploadsProxyTarget = process.env.PLANE_WEB_UPLOADS_PROXY_TARGET || "http://127.0.0.1:9300";

export default defineConfig(({ command }) => {
  const clientEnv = { ...viteEnv };

  if (command === "serve") {
    // Keep browser requests on the current host when development is opened via a LAN/VPN host name.
    clientEnv.VITE_API_BASE_URL = "";
    clientEnv.VITE_WEB_BASE_URL = "";
    clientEnv.VITE_LIVE_BASE_URL = "";
    clientEnv.VITE_LIVE_BASE_PATH = process.env.VITE_LIVE_BASE_PATH || "/live";
  }

  return {
    define: {
      "process.env": JSON.stringify(clientEnv),
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
      proxy: {
        "/api": { target: apiProxyTarget, changeOrigin: false },
        "/auth": { target: apiProxyTarget, changeOrigin: false },
        "/static": { target: apiProxyTarget, changeOrigin: false },
        "/uploads": { target: uploadsProxyTarget, changeOrigin: false },
        "/live": { target: liveProxyTarget, changeOrigin: true, ws: true },
      },
    },
    // No SSR-specific overrides needed; alias resolves to ESM build
  };
});
