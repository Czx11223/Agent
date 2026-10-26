export interface SseEvent {
  type?: string;
  delta?: string;
  text?: string;
  [key: string]: unknown;
}

/**
 * POST 流式请求并逐事件回调。
 * 兼容两类报文：
 *   event:<name>\ndata:{JSON}\n\n
 *   data:{"type":..., ...}\n\n
 * 说明：POST 流式无法使用 EventSource（其仅限 GET），故用 Fetch + ReadableStream。
 */
export async function streamPost(
  url: string,
  body: unknown,
  token: string,
  onEvent: (ev: SseEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      Accept: "text/event-stream",
      "Cache-Control": "no-cache"
    },
    body: JSON.stringify(body),
    signal
  });
  if (!res.body) throw new Error("no stream body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";
  let eventName = "";

  const emit = (dataLine: string, name: string) => {
    if (!dataLine) return;
    try {
      const parsed = JSON.parse(dataLine);
      onEvent(name ? { type: name, ...parsed } : parsed);
    } catch {
      /* 忽略不完整帧 */
    }
  };

  const feed = (chunk: string) => {
    buf += chunk;
    const parts = buf.split("\n\n");
    buf = parts.pop() ?? "";
    for (const part of parts) {
      eventName = "";
      let dataLine = "";
      for (const line of part.split("\n")) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLine += line.slice(5).trim();
      }
      if (dataLine) emit(dataLine, eventName);
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    feed(decoder.decode(value, { stream: true }));
  }
  feed(decoder.decode());
}