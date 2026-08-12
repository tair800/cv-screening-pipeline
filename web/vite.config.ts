import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API is proxied rather than called cross-origin: in dev the browser sees one origin,
// so there is no CORS configuration to write here and none to forget in production.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.API_URL ?? "http://127.0.0.1:8017",
        changeOrigin: true,
      },
    },
  },
});
