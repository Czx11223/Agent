import axios from "axios";

export const TOKEN_KEY = "icd_token";
export const getToken = (): string | null => localStorage.getItem(TOKEN_KEY);
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

const http = axios.create({ baseURL: "/api/v1", timeout: 15000 });

http.interceptors.request.use((cfg) => {
  const t = getToken();
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

http.interceptors.response.use(
  (r) => r.data?.data ?? r.data,
  (err) => Promise.reject(err?.response?.data?.message ?? err?.message ?? "请求失败")
);

export interface Conversation {
  id: number;
  title: string | null;
  status: string;
}
export interface MessageInfo {
  id: number;
  sender: "user" | "agent";
  content: string;
}

export const register = (d: { username: string; password: string; phone?: string }) =>
  http.post("/auth/register", d);
export const login = (d: { account: string; password: string }) => http.post("/auth/login", d);
export const listConversations = (): Promise<Conversation[]> => http.get("/conversations") as unknown as Promise<Conversation[]>;
export const createConversation = (title?: string): Promise<{ conversation_id: number }> =>
  http.post("/conversations", { title }) as unknown as Promise<{ conversation_id: number }>;
export const getConversationMessages = (cid: number): Promise<{ messages: MessageInfo[] }> =>
  http.get(`/conversations/${cid}/messages`) as unknown as Promise<{ messages: MessageInfo[] }>;
export const getReport = (cid: number): Promise<Record<string, unknown>> =>
  http.get(`/reports/${cid}`) as unknown as Promise<Record<string, unknown>>;
export const getExport = (cid: number): Promise<{ content: string }> =>
  http.get(`/reports/${cid}/export`) as unknown as Promise<{ content: string }>;

export default http;