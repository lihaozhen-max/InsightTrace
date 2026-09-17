import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createConversation, listConversations } from "../api/conversations";

export function ConversationWorkspace() {
  const [title, setTitle] = useState("");
  const queryClient = useQueryClient();
  const conversations = useQuery({
    queryKey: ["conversations"],
    queryFn: listConversations,
  });
  const createMutation = useMutation({
    mutationFn: createConversation,
    onSuccess: async () => {
      setTitle("");
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedTitle = title.trim();
    if (normalizedTitle) {
      createMutation.mutate(normalizedTitle);
    }
  }

  return (
    <section className="workspace" aria-labelledby="workspace-title">
      <div className="workspace-heading">
        <div>
          <p className="eyebrow">M2 · 会话工作台</p>
          <h2 id="workspace-title">我的分析会话</h2>
        </div>
        <form className="conversation-form" onSubmit={handleSubmit}>
          <label htmlFor="conversation-title">新会话标题</label>
          <div>
            <input
              id="conversation-title"
              value={title}
              maxLength={200}
              placeholder="例如：分析本月商品转化下降原因"
              onChange={(event) => setTitle(event.target.value)}
            />
            <button type="submit" disabled={!title.trim() || createMutation.isPending}>
              {createMutation.isPending ? "创建中…" : "创建会话"}
            </button>
          </div>
        </form>
      </div>

      {conversations.isPending && <p className="muted">正在读取会话……</p>}
      {conversations.isError && <p className="error">会话列表读取失败，请稍后重试。</p>}
      {createMutation.isError && <p className="error">创建失败，请检查标题后重试。</p>}

      {conversations.data?.length === 0 && (
        <div className="empty-state">
          <strong>还没有分析会话</strong>
          <p>输入一个经营问题作为标题，创建你的第一条会话。</p>
        </div>
      )}

      {conversations.data && conversations.data.length > 0 && (
        <ul className="conversation-list">
          {conversations.data.map((conversation) => (
            <li key={conversation.id}>
              <div>
                <strong>{conversation.title}</strong>
                <span>{new Date(conversation.created_at).toLocaleString("zh-CN")}</span>
              </div>
              <span className="status-pill">
                {conversation.status === "active" ? "进行中" : "已归档"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
