import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5173,
    // 本地开发：/api 代理到 FastAPI 后端（透传 SSE，关闭代理缓冲）
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true }
    }
  },
  build: { outDir: "dist" }
});