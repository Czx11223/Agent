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
  onStreamDone?: (next: string, text: string) => void;
}

export function ChatWindow({ conversationId, history = [], onStreamDone }: Props) {
  const [messages, setMessages] = useState<ChatMsg[]>(history);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const rafRef = useRef<number>(0);
  const pendingRef = useRef("");

  useEffect(() => { setMessages(history); }, [history]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const flushPending = () => {
    rafRef.current = 0;
    const delta = pendingRef.current;
    pendingRef.current = "";
    if (!delta) return;
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last && last.sender === "agent" && last.streaming) {
        next[next.length - 1] = { ...last, content: last.content + delta };
      } else {
        next.push({ id: `a-${Date.now()}`, sender: "agent", content: delta, streaming: true });
      }
      return next;
    });
  };

  // 高频 delta 合并到下一帧统一渲染，避免卡顿
  const appendDelta = (delta: string) => {
    pendingRef.current += delta;
    if (!rafRef.current) rafRef.current = requestAnimationFrame(flushPending);
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
            case "comfort":
              if (ev.text) appendDelta(String(ev.text));
              break;
            case "question":
              if (ev.text) appendDelta(String(ev.text));
              break;
            case "done":
              if (ev.text) appendDelta(String(ev.text ?? ""));
              onStreamDone?.(String(ev.next ?? ""), String(ev.text ?? ""));
              break;
            case "error":
              appendDelta(String(ev.text ?? "服务出错，请重试"));
              break;
            default:
              if (typeof ev.text === "string") appendDelta(ev.text);
          }
        },
        abortRef.current.signal
      );
    } catch (e) {
      appendDelta(`\n\n[连接中断] ${String(e)}，请重试`);
    } finally {
      if (rafRef.current) window.cancelAnimationFrame(rafRef.current);
      flushPending();
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
                m.sender === "user" ? "bg-blue-500 text-white" : "bg-slate-100 text-slate-800"
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