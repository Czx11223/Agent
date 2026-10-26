import { Button, Empty, List, Skeleton } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import type { Conversation } from "../services/api";

interface Props {
  conversations: Conversation[];
  activeId: number | null;
  loading?: boolean;
  onSelect: (id: number) => void;
  onNew: () => void;
  onClose?: () => void;
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
              style={{
                cursor: "pointer",
                paddingLeft: 12,
                paddingRight: 12,
                background: c.id === activeId ? "#eff6ff" : undefined
              }}
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