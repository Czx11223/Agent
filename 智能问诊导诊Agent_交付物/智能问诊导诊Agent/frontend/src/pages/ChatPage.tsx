import { useCallback, useEffect, useState } from "react";
import { Button, Drawer } from "antd";
import { MenuOutlined, LogoutOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { ConversationList, type Conversation as Conv } from "../components/ConversationList";
import { ChatWindow, type ChatMsg } from "../components/ChatWindow";
import { ReportPanel, type Report } from "../components/ReportPanel";
import {
  listConversations,
  createConversation,
  getConversationMessages,
  getReport,
  clearToken
} from "../services/api";

interface RawMsg { id: number; sender: "user" | "agent"; content: string }

export default function ChatPage() {
  const [convs, setConvs] = useState<Conv[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [history, setHistory] = useState<ChatMsg[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [showReport, setShowReport] = useState(false);
  const [loading, setLoading] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const nav = useNavigate();

  const loadConvs = useCallback(async () => {
    setLoading(true);
    try { setConvs(await listConversations()); } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadConvs(); }, [loadConvs]);

  const selectConv = useCallback(async (cid: number) => {
    setActiveId(cid);
    setReport(null);
    setShowReport(false);
    const d = await getConversationMessages(cid);
    setHistory(
      (d.messages ?? []).map((m: RawMsg) => ({
        id: String(m.id),
        sender: m.sender,
        content: m.content
      }))
    );
  }, []);

  const handleNew = useCallback(async () => {
    const d = await createConversation();
    await loadConvs();
    setActiveId(d.conversation_id);
    setHistory([]);
    setReport(null);
    setShowReport(false);
  }, [loadConvs]);

  const handleStreamDone = useCallback(
    async (next: string) => {
      if (next === "report_ready" && activeId) {
        const r = (await getReport(activeId)) as Report;
        setReport(r);
        setShowReport(true);
      }
    },
    [activeId]
  );

  const logout = () => {
    clearToken();
    nav("/login");
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-50">
      {/* PC 侧栏 */}
      <div className="hidden md:block">
        <ConversationList conversations={convs} activeId={activeId} loading={loading}
                          onSelect={selectConv} onNew={handleNew} />
      </div>
      {/* 移动端 Drawer */}
      <div className="md:hidden" />
      <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)} placement="left" width={280}
              title="会话列表" extra={<Button icon={<LogoutOutlined />} onClick={logout} type="text" />}>
        <div className="flex h-full flex-col">
          <ConversationList conversations={convs} activeId={activeId} loading={loading}
                            onSelect={selectConv} onNew={handleNew} onClose={() => setDrawerOpen(false)} />
        </div>
      </Drawer>

      <main className="flex flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-slate-200 bg-white px-3 py-2 md:hidden">
          <Button icon={<MenuOutlined />} onClick={() => setDrawerOpen(true)} type="text" />
          <span className="flex-1 truncate text-sm font-medium">
            {activeId ? (convs.find((c) => c.id === activeId)?.title || `会话#${activeId}`) : "智能问诊导诊"}
          </span>
          <Button icon={<LogoutOutlined />} onClick={logout} type="text" />
        </div>

        {activeId ? (
          report && showReport ? (
            <ReportPanel report={report} />
          ) : (
            <ChatWindow conversationId={activeId} history={history} onStreamDone={handleStreamDone} />
          )
        ) : (
          <div className="flex flex-1 items-center justify-center text-slate-400">
            选择或新建一个问诊会话开始
          </div>
        )}
      </main>
    </div>
  );
}