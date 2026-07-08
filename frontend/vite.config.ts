import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, path.resolve(__dirname, ".."), "");
  const backendUrl = env.VITE_BACKEND_URL || "http://localhost:8000";
  const wsTarget = backendUrl.replace(/^http/, "ws");

  console.log(`[Vite] Proxying /api and /ws to: ${backendUrl}`);

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      proxy: {
        "/api": backendUrl,
        "/workspace": backendUrl,
        "/ws": { target: wsTarget, ws: true },
      },
    },
    build: {
      rollupOptions: {
        onwarn(warning, warn) {
          // vendored AI Elements files carry "use client" directives (no-op in Vite)
          if (warning.code === "MODULE_LEVEL_DIRECTIVE") return;
          warn(warning);
        },
      },
    },
  };
});
