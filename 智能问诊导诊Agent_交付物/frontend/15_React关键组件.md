# React 前端关键组件代码

- 版本：V1.0.0　·　技术栈：React 18 + TypeScript(strict) + Vite 5 + TailwindCSS 3 + Ant Design 5 + react-router 6 + axios
- 对接后端：`/api/v1/*`，SSE 对话接口 `POST /api/v1/chat/stream`（`text/event-stream`）
- 适配：PC 左侧会话列表 + 右侧聊天；移动端全屏对话（响应式）

> ⚠️ **说明**：因 SSE 接口是 `POST`，浏览器 `EventSource`（仅 GET）不适用，故使用 **Fetch + ReadableStream** 手动解析 SSE。

---

## 1. SSE 流式客户端 `src/services/sse.ts`

```ts
// src/services/sse.ts
export interface SseEvent {
  type?: string;            // 事件名：chat中的事件或此后端 event 名
  [key: string]: unknown;
}

/**
 * POST 流式请求并逐事件回调。
 * 兼容两种报文：`event:<name>\ndata:{...}\n\n` 与 `data:{"type":...}\n\n`
 */
export async function streamPost(
  url: string,
  body: unknown,
  token: string,
  onEvent: (ev: SseEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      Accept: "text/event-stream",
      "Cache-Control": "no-cache",
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.body) throw new Error("no stream body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";
  let currentEvent = "";

  const handleDispatch = (eventLine: string, dataLine: string) => {
    if (!dataLine) return;
    try {
      onEvent({ type: eventLine || JSON.parse(dataLine).type, ...JSON.parse(dataLine) });
    } catch {
      /* 忽略无法解析的残缺帧 */
    }
  };

  // 说明：严格按 SSE 报文的空行分隔解析
  const feed = (chunk: string) => {
    buf += chunk;
    const parts = buf.split("\n\n");
    buf = parts.pop() ?? "";
    for (const part of parts) {
      currentEvent = "";
      let dataLine = "";
      for (const line of part.split("\n")) {
        if (line.startsWith("event:")) currentEvent = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLine += line.slice(5).trim();
      }
      if (dataLine) handleDispatch(currentEvent, dataLine);
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    feed(decoder.decode(value, { stream: true }));
  }
  feed(decoder.decode());
}
```

---

## 2. API 客户端 `src/services/api.ts`

```ts
// src/services/api.ts
import axios from "axios";

export const TOKEN_KEY = "icd_token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);

const http = axios.create({ baseURL: "/api/v1", timeout: 15000 });

http.interceptors.request.use((cfg) => {
  const t = getToken();
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});
// 统一错误处理：code!=0 用 message；401 跳登录
http.interceptors.response.use(
  (r) => r.data?.data ?? r.data,
  (err) => Promise.reject(err.response?.data?.message ?? "请求失败"),
);

// ---- 认证 ----
export const register = (d: { username: string; password: string; phone?: string }) =>
  http.post("/auth/register", d);
export const login = (d: { account: string; password: string }) => http.post("/auth/login", d);

// ---- 会话 ----
export interface Conversation { id: number; title: string; status: string; [k: string]: unknown }
export const listConversations = () => http.get("/conversations");
export const createConversation = (title?: string) => http.post("/conversations", { title });
export const getConversationMessages = (cid: number) => http.get(`/conversations/${cid}/messages`);

// ---- 报告 ----
export const getReport = (cid: number) => http.get(`/reports/${cid}`);
export const exportReport = (cid: number) => http.get<{ content: string }>(`/reports/${cid}/export`);

export default http;
```

---

## 3. 会话列表组件 `src/components/ConversationList.tsx`

```tsx
// src/components/ConversationList.tsx
import { Button, Empty, List, Skeleton } from "antd";
import { PlusOutlined } from "@ant-design/icons";

export interface Conversation { id: number; title: string; status: string }

interface Props {
  conversations: Conversation[];
  activeId: number | null;
  loading?: boolean;
  onSelect: (id: number) => void;
  onNew: () => void;
  onClose?: () => void;   // 移动端 drawer 关闭
}

export function ConversationList({ conversations, activeId, loading, onSelect, onNew, onClose }: Props) {
  return (
    <aside className="flex h-full w-72 flex-col border-r border-slate-200 bg-white md:w-80">
      <div className="p-3">
        <Button type="primary" icon={<PlusOutlined />} block onClick={onNew}>
          新建问诊
        </Button>
      </div>
      {loading ? (
        <div className="px-3"><Skeleton active /></div>
      ) : conversations.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无会话" />
      ) : (
        <List
          className="flex-1 overflow-y-auto"
          dataSource={conversations}
          renderItem={(c) => (
            <List.Item
              onClick={() => { onSelect(c.id); onClose?.(); }}
              className={`cursor-pointer px-3 ${c.id === activeId ? "bg-blue-50" : ""}`}
            >
              <List.Item.Meta
                title={c.title || `会话#${c.id}`}
                description={c.status === "completed" ? "已完成" : "问诊中"}
              />
            </List.Item>
          )}
        />
      )}
    </aside>
  );
}
```

---

## 4. 聊天对话主组件 `src/components/ChatWindow.tsx`

含消息气泡、滚动到底部、SSE 流式追加。

```tsx
// src/components/ChatWindow.tsx
import { useEffect, useRef, useState } from "react";
import { Button, Input } from "antd";
import { SendOutlined } from "@ant-design/icons";
import { streamPost } from "../services/sse";
import { getToken } from "../services/api";

export interface ChatMsg {
  id: string;
  sender: "user" | "agent";
  content: string;
  streaming?: boolean;
}

interface Props {
  conversationId: number;
  history?: ChatMsg[];
  onStreamDone?: (next: string, text: string) => void;  // done事件，report_ready时触发
}

export function ChatWindow({ conversationId, history = [], onStreamDone }: Props) {
  const [messages, setMessages] = useState<ChatMsg[]>(history);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => { setMessages(history); }, [history]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  // 追加流式片段到"最后一条 agent 消息"
  const appendDelta = (delta: string) => {
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last?.sender === "agent" && last.streaming) {
        next[next.length - 1] = { ...last, content: last.content + delta };
      } else {
        next.push({ id: `a-${Date.now()}`, sender: "agent", content: delta, streaming: true });
      }
      return next;
    });
  };

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setSending(true);
    setMessages((m) => [...m, { id: `u-${Date.now()}`, sender: "user", content: text }]);
    abortRef.current = new AbortController();

    try {
      await streamPost(
        "/api/v1/chat/stream",
        { conversation_id: conversationId, content: text },
        getToken() ?? "",
        (ev) => {
          switch (ev.type) {
            case "token":
              if (ev.delta) appendDelta(String(ev.delta));
              break;
            case "question":
            case "done":
              if (ev.text && ev.type === "question") appendDelta(String(ev.text));
              if (ev.type === "done") {
                onStreamDone?.(String(ev.next ?? ""), String(ev.text ?? ""));
              }
              break;
            case "comfort":
              if (ev.text) appendDelta(String(ev.text));
              break;
            default:
              if (typeof ev.text === "string") appendDelta(ev.text);
          }
        },
        abortRef.current.signal,
      );
    } catch (e) {
      appendDelta(`\n\n[系统] ${String(e)}`);
    } finally {
      setMessages((m) => m.map((x) => (x.streaming ? { ...x, streaming: false } : x)));
      setSending(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {messages.map((m) => (
          <div key={m.id} className={`flex ${m.sender === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[78%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm ${
                m.sender === "user"
                  ? "bg-blue-500 text-white"
                  : "bg-slate-100 text-slate-800"
              }`}
            >
              {m.content}
              {m.streaming && <span className="ml-1 inline-block animate-pulse">▍</span>}
            </div>
          </div>
        ))}
      </div>

      <div className="border-t border-slate-200 p-3">
        <Input.TextArea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={() => send()}
          placeholder="描述您的症状，例如：我胸口疼三天了"
          autoSize={{ minRows: 1, maxRows: 4 }}
          maxLength={1024}
          disabled={sending}
        />
        <div className="mt-2 flex justify-end">
          <Button type="primary" icon={<SendOutlined />} loading={sending} onClick={send}>
            发送
          </Button>
        </div>
      </div>
    </div>
  );
}
```

---

## 5. 预问诊报告展示组件 `src/components/ReportPanel.tsx`

含 Markdown 渲染、科室推荐 Top3、免责声明、复制与导出。

```tsx
// src/components/ReportPanel.tsx
import { useMemo } from "react";
import { Button, Card, Descriptions, Tag, Typography } from "antd";
import ReactMarkdown from "react-markdown";
import { CopyOutlined, DownloadOutlined } from "@ant-design/icons";

const { Title, Paragraph, Text } = Typography;

export interface Report {
  chief_complaint?: string | null;
  present_illness?: string | null;
  allergy_history?: string | null;
  past_history?: string | null;
  recommend_dept_top3?: string | null;  // JSON: [{dept,reason}]
  disclaimer?: string | null;
}

/** 解析 Top3 科室推荐（兼容 JSON 字符串） */
function parseDepts(raw?: string | null): { dept: string; reason?: string }[] {
  if (!raw) return [];
  try {
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr : [];
  } catch {
    return [{ dept: raw }];
  }
}

export function ReportPanel({ report }: { report: Report }) {
  const depts = useMemo(() => parseDepts(report.recommend_dept_top3), [report.recommend_dept_top3]);

  // 生成 Markdown 报告文本（用于复制/导出）
  const md = useMemo(
    () => `# 预问诊报告

## 主诉
${report.chief_complaint ?? "未提供"}

## 现病史
${report.present_illness ?? "未提供"}

## 过敏史
${report.allergy_history ?? "无已知药物/食物过敏"}

## 既往史
${report.past_history ?? "未提供"}

## 科室推荐
${depts.map((d, i) => `${i + 1}. ${d.dept}：${d.reason ?? ""}`).join("\n")}

> ${report.disclaimer ?? "本报告来源于患者口述，仅供参考。"}`,
    [report, depts],
  );

  const copy = async () => {
    try { await navigator.clipboard.writeText(md); } catch { /* 降级忽略 */ }
  };
  const download = () => {
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `pre_diagnose_report.md`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div className="space-y-3">
      <Card className="w-full">
        <Title level={5} style={{ marginTop: 0 }}>预问诊报告</Title>
        {/* 科室推荐 Top3 */}
        <div className="mb-4 flex flex-wrap gap-2">
          {depts.map((d, i) => (
            <Tag key={d.dept + i} color={i === 0 ? "blue" : "default"} className="py-1 px-3">
              <span className="font-semibold">{i + 1}. {d.dept}</span>
              {d.reason && <Text type="secondary" className="ml-1 text-xs">{d.reason}</Text>}
            </Tag>
          ))}
        </div>

        {/* Markdown 渲染 */}
        <div className="prose prose-sm max-w-none">
          <ReactMarkdown>
            {md}
          </ReactMarkdown>
        </div>

        <div className="mt-4 flex gap-2">
          <Button icon={<CopyOutlined />} onClick={copy}>复制报告</Button>
          <Button icon={<DownloadOutlined />} onClick={download}>导出 .md</Button>
        </div>
      </Card>

      {/* 常驻免责声明 */}
      <Paragraph className="mb-0 text-center">
        <Text type="secondary" className="text-xs">
          {report.disclaimer ?? "本预问诊报告仅用于挂号与接诊参考，不构成医学诊断或治疗建议，最终请以执业医师判断为准。"}
        </Text>
      </Paragraph>
    </div>
  );
}
```

---

## 6. 页面组装（示意）`src/pages/ChatPage.tsx` + `src/App.tsx`

```tsx
// src/pages/ChatPage.tsx —— 主对话页：左侧会话列表 + 右侧聊天 / 报告
import { useEffect, useState } from "react";
import { Drawer } from "antd";
import { ConversationList, Conversation } from "../components/ConversationList";
import { ChatWindow, ChatMsg } from "../components/ChatWindow";
import { ReportPanel, Report } from "../components/ReportPanel";
import { listConversations, createConversation, getConversationMessages, getReport } from "../services/api";

export function ChatPage() {
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [history, setHistory] = useState<ChatMsg[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [showReport, setShowReport] = useState(!isMobile());
  const [drawerOpen, setDrawerOpen] = useState(false);

  const loadConvs = () => listConversations().then((d) => setConvs(d));

  useEffect(() => { loadConvs(); }, []);

  const selectConv = async (cid: number) => {
    setActiveId(cid); setReport(null);
    const d = await getConversationMessages(cid);
    setHistory((d.messages ?? []).map((m) => ({
      id: String(m.id), sender: m.sender, content: m.content,
    })));
  };

  const handleNew = async () => {
    const d = await createConversation();
    await loadConvs();
    setActiveId(d.conversation_id); setHistory([]); setReport(null);
  };

  // done事件: next === "report_ready" 时拉取报告
  const handleStreamDone = async (next: string, _text: string) => {
    if (next === "report_ready" && activeId) {
      const r = await getReport(activeId);
      setReport(r);
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-50">
      {/* PC: 固定侧栏；移动: Drawer */}
      <div className="hidden md:block">
        <ConversationList conversations={convs} activeId={activeId}
                          onSelect={selectConv} onNew={handleNew} />
      </div>
      <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)}
              placement="left" width={280} title="会话列表">
        <ConversationList conversations={convs} activeId={activeId}
                          onSelect={selectConv} onNew={handleNew} onClose={() => setDrawerOpen(false)} />
      </Drawer>

      <main className="flex flex-1 flex-col">
        {activeId ? (
          report && showReport ? (
            <ReportPanel report={report} />
          ) : (
            <ChatWindow conversationId={activeId} history={history} onStreamDone={handleStreamDone} />
          )
        ) : (
          <EmptyState />
        )}
      </main>
    </div>
  );
}

function isMobile() { return typeof window !== "undefined" && window.innerWidth < 768; }
function EmptyState() { return <div className="flex flex-1 items-center justify-center text-slate-400">选择或新建一个问诊会话开始</div>; }
```

```tsx
// src/App.tsx —— 路由
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { LoginPage, RegisterPage } from "./pages/AuthPage";
import { ChatPage } from "./pages/ChatPage";
import { getToken } from "./services/api";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/chat"
               element={getToken() ? <ChatPage /> : <Navigate to="/login" replace />} />
        <Route path="*" element={<Navigate to="/chat" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
```