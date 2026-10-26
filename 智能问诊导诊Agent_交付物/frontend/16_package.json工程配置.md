# 前端工程配置（package.json 与工程依赖）

- 版本：V1.0.0　·　工具链：Vite 5 + React 18 + TypeScript(strict)

---

## 1. package.json

```json
{
  "name": "inquiry-guide-agent-web",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@ant-design/icons": "^5.3.7",
    "antd": "^5.19.0",
    "axios": "^1.7.2",
    "dayjs": "^1.11.11",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-markdown": "^9.0.1",
    "react-router-dom": "^6.24.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.39",
    "tailwindcss": "^3.4.6",
    "typescript": "^5.5.3",
    "vite": "^5.3.3"
  }
}
```

---

## 2. TypeScript 配置 `tsconfig.json`（strict）

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  },
  "include": ["src"]
}
```

---

## 3. Vite 配置 `vite.config.ts`

```ts
// vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5173,
    // 本地开发代理：对接 FastAPI 后端，并透传 SSE
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true }
    }
  },
  build: { outDir: "dist" }
});
```

> 生产环境：`dist` 由 Nginx 托管，`/api` 反向代理到后端（HTTPS 终截，见后端文档 `[TLS]` 说明）。

---

## 4. TailwindCSS 配置 `tailwind.config.js` + `postcss.config.js`

```js
// tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: []
};
```

```js
// postcss.config.js
export default { plugins: { tailwindcss: {}, autoprefixer: {} } };
```

---

## 5. 入口与样式 `index.html` + `src/index.css`

```html
<!-- index.html -->
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>智能问诊导诊</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

```css
/* src/index.css — Tailwind 指令 */
@tailwind base;
@tailwind components;
@tailwind utilities;

/* 让 ReactMarkdown 内的标题/列表更易读 */
.prose h1, .prose h2 { @apply text-base font-semibold; margin: 0.5rem 0; }
.prose p { @apply text-sm leading-6; }
```

---

## 6. 入口 `src/main.tsx`（示意）

```tsx
// src/main.tsx
import { createRoot } from "react-dom/client";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { App } from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <ConfigProvider locale={zhCN}>
    <App />
  </ConfigProvider>
);
```

---

## 7. 安装与启动

```bash
npm install
npm run dev            # 本地, Vite dev server + /api 代理到后端
npm run build          # 类型检查 + 产出 dist/
```