# 智能问诊导诊 Agent Web · 优化方案

- 版本：V1.0.0　·　定位：在《24_性能优化与BadCase迭代方案》之上，聚焦 **Web 层可落地的优化**（前端渲染/包体、后端接口/数据库、SSE 体验、安全加固）。
- 每项标 难度 与 收益，供排期；附代码级改动示例。

---

## 第 1 章 前端优化

### 1.1 包体积与首屏

| 手段 | 改动示例 | 收益 |
| --- | --- | --- |
| **AntD 按需引入** | `import { Button } from "antd"` + `import "antd/dist/reset.css"`，配 babel-plugin-import 或直接靠 ESM tree-shaking | 显著 |
| **路由懒加载** | `const ChatPage = lazy(() => import("./pages/ChatPage"))` | 首屏只载登录页 |
| 压缩+gzip | Vite build `build.rollupOptions.output.manualChunks` 分 vendor/antd/react | 中 |
| 禁用 pro 图标整包 | 仅 `import "@ant-design/icons/es/icons/..."` 或用 `unplugin-icons` | 小 |

```tsx
// 路由懒加载 + 分包分包示例（App.tsx）
import { lazy, Suspense } from "react";
const ChatPage = lazy(() => import("./pages/ChatPage"));
const AuthPage = lazy(() => import("./pages/AuthPage"));
// 用 <Suspense fallback={<Spin />}> 包裹 Routes
```

### 1.2 渲染与交互体验

| 手段 | 代码要点 |
| --- | --- |
| **SSE 即时渲染** | `sse.ts` 每收一个 `token` 帧即 `appendDelta`，避免 batch；用 `requestAnimationFrame` 合并高频帧防卡顿 |
| 消息列表**虚拟滚动** | 会话历史多时用 `react-window` 渲染可见项，滚动触底加载 |
| 输入节流/防抖 | 发送按钮 `disabled={sending}`；`onPressEnter` 防重复提交 |
| 滚动锚定 | 新消息到达时 `scrollTo`，仅当用户未上翻时自动滚底 |
| 骨架屏 | 报告生成时 `ChatWindow` 显示 loading 气泡，避免空白 |

```tsx
// 流式帧合并（ChatWindow 内）：高频 delta 用 RAF 合并再 append
const pending = useRef("");
const raf = useRef<number>(0);
const flush = () => { appendDelta(pending.current); pending.current = ""; };
// 收到 token 帧: pending.current += delta; raf.current ||= requestAnimationFrame(flush);
```

### 1.3 状态管理

- 会话/消息状态收敛到 `ChatPage`，组件 props 传递，避免全局 store 过度；仅 token 与 user 放 localStorage。
- 报告数据仅当 `report_ready` 时拉取，切换会话即 `setReport(null)` 防串数据。

---

## 第 2 章 后端 / 接口优化

| 项 | 手段 | 示例 |
| --- | --- | --- |
| **慢查询** | message/conversation 建索引；仅按需查字段 | `CREATE INDEX idx_msg_conv ON message(conversation_id);` |
| **连接管理** | sqlite WAL + `check_same_thread=False` + 每线程连接；写入批处理 | 见《03/12》DDL 与 db.py |
| **异步化** | LLM 调用走 `async`/线程池，不阻塞事件循环；`httpx.AsyncClient` 复用连接 | — |
| **限流** | 登录/对话接口加 `slowapi` 速率限制（防刷） | `@limiter.limit("10/minute")` |
| **响应裁剪** | 列表接口分页 `page/limit`，避免整表返回 | `GET /conversations?page=1&size=20` |
| **接口缓存头** | 症状-科室映射表经 `Cache-Control` 静态缓存 | 预热进内存即可 |

```python
# 会话历史分页（router 示意）
@app.get("/conversations/{cid}/messages")
def messages(cid: int, page: int = 1, size: int = 20):
    rows = db.fetch_page(cid, page, size)   # LIMIT ? OFFSET ?
    return {"messages": rows}
```

---

## 第 3 章 SSE 流式体验优化

| 问题 | 优化 | 说明 |
| --- | --- | --- |
| 长回复断感 | 首帧秒回 + 前端 RAF 合帧渲染 | 已实现 |
| 网络抖动断连 | **心跳注释**：后端可发 `: keep-alive`，前端监听 `error` 显示重连 | 前端 catch → 提示"连接中断，可重试" |
| 代理缓冲 | 设 `X-Accel-Buffering: no` + Nginx `proxy_buffering off` | 已写入 18 章 |
| 重复流程 | 完成后前端 `signal.abort()` 中止滞留流，避免状态残留 | `abortRef` |
| 事件清晰化 | 统一事件：`token / comfort / emergency / rejected / question / done` | 已定义 |

```ts
// 前端：断连处理（ChatWindow）
catch (e) { appendDelta("\n[连接中断] 请重试"); setSending(false); }
```

---

## 第 4 章 安全加固补充

| 项 | 措施 |
| --- | --- |
| 输入 | `sanitize_text` 长度+白名单+注入模式过滤（4007），前端同样 `maxLength` |
| 认证 | JWT 过期刷新、登出清理 token、密码 bcrypt+盐 |
| 越权 | 所有会话/报告按 `user_id` 归属校验（4004） |
| 传输 | 生产 HTTPS 终截、密钥不进前端（`[TLS]`） |
| CORS | 仅放行前端真实域名，勿 `*`+credentials |
| 前端 | 用户内容一律转义渲染，杜绝 XSS；报告用 `react-markdown` 默认安全 |

---

## 第 5 章 优化优先级与验收

| 优先级 | 项 | 对应指标/收益 | 工作量 |
| --- | --- | --- | --- |
| P0 | SSE 即时渲染 + 断连处理 | 感知时延↓、健壮性 | 低 |
| P0 | 慢查询索引 + 分页 | 历史/列表稳定快 | 低 |
| P1 | 路由懒加载 + antd 按需 | 首屏体积↓ | 中 |
| P1 | 限流 + 越权复核 | 安全等级↑ | 中 |
| P1 | 消息虚拟滚动 | 长会话流畅 | 中 |
| P2 | 粘连缓存/映射预热（24章） | 平均响应≤5s | 中 |

**验收口径**：回归《22》用例集不回归；首屏 < 3s（P50）、长历史滚动流畅、SSE 断连可恢复、安全用例全过；核心指标（覆盖率≥90%、完整率≥90%、Top3≥80%、均响应≤5s）达标。

---

## 附：落地清单（按文件）

| 文件 | 改动 |
| --- | --- |
| `frontend/src/App.tsx` | 路由 lazy + Suspense |
| `frontend/src/components/ChatWindow.tsx` | RAF 合帧、断连提示、abort |
| `frontend/src/pages/ChatPage.tsx` | 状态收敛、切换清报告 |
| `backend/app/routers/conversation.py` | 分页、索引保障 |
| `backend/app/routers/chat.py` | 限流、SSE 心跳、超时 |
| `backend/app/core/security.py` | 越权校验、输入过滤复核 |
| `deploy/nginx.conf` | proxy_buffering off、gzip、HTTPS |