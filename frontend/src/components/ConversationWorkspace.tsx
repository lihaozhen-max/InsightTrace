import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createConversation,
  deleteConversation,
  listConversations,
  listMessages,
  updateConversation,
} from "../api/conversations";
import { AttachmentPanel } from "./AttachmentPanel";
import { TaskPanel } from "./TaskPanel";

export function ConversationWorkspace() {
  const [title, setTitle] = useState("");
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [editingConversationId, setEditingConversationId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const queryClient = useQueryClient();
  const conversations = useQuery({
    queryKey: ["conversations"],
    queryFn: listConversations,
  });
  const messages = useQuery({
    queryKey: ["messages", selectedConversationId],
    queryFn: () => listMessages(selectedConversationId!),
    enabled: selectedConversationId !== null,
  });
  const createConversationMutation = useMutation({
    mutationFn: createConversation,
    onSuccess: async (conversation) => {
      setTitle("");
      setSelectedConversationId(conversation.id);
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });
  const updateConversationMutation = useMutation({
    mutationFn: updateConversation,
    onSuccess: async () => {
      setEditingConversationId(null);
      setEditingTitle("");
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });
  const deleteConversationMutation = useMutation({
    mutationFn: deleteConversation,
    onSuccess: async (_, conversationId) => {
      if (selectedConversationId === conversationId) {
        setSelectedConversationId(null);
      }
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  function handleConversationSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedTitle = title.trim();
    if (normalizedTitle) {
      createConversationMutation.mutate(normalizedTitle);
    }
  }

  function handleRenameSubmit(event: FormEvent<HTMLFormElement>, conversationId: string) {
    event.preventDefault();
    const normalizedTitle = editingTitle.trim();
    if (normalizedTitle) {
      updateConversationMutation.mutate({ conversationId, title: normalizedTitle });
    }
  }

  function beginRename(conversationId: string, currentTitle: string) {
    setEditingConversationId(conversationId);
    setEditingTitle(currentTitle);
  }

  function handleDelete(conversationId: string, conversationTitle: string) {
    const confirmed = window.confirm(
      `确定删除“${conversationTitle}”吗？该会话中的消息也会一起删除。`,
    );
    if (confirmed) {
      deleteConversationMutation.mutate(conversationId);
    }
  }

  const selectedConversation = conversations.data?.find(
    (conversation) => conversation.id === selectedConversationId,
  );

  return (
    <section className="workspace" aria-labelledby="workspace-title">
      <div className="workspace-heading">
        <div>
          <p className="eyebrow">M5 · 归因分析工作台</p>
          <h2 id="workspace-title">我的分析会话</h2>
        </div>
        <form className="conversation-form" onSubmit={handleConversationSubmit}>
          <label htmlFor="conversation-title">新会话标题</label>
          <div>
            <input
              id="conversation-title"
              value={title}
              maxLength={200}
              placeholder="例如：分析本月商品转化下降原因"
              onChange={(event) => setTitle(event.target.value)}
            />
            <button
              type="submit"
              disabled={!title.trim() || createConversationMutation.isPending}
            >
              {createConversationMutation.isPending ? "创建中…" : "创建会话"}
            </button>
          </div>
        </form>
      </div>

      {conversations.isPending && <p className="muted">正在读取会话……</p>}
      {conversations.isError && <p className="error">会话列表读取失败，请稍后重试。</p>}
      {createConversationMutation.isError && (
        <p className="error">创建失败，请检查标题后重试。</p>
      )}

      {conversations.data?.length === 0 && (
        <div className="empty-state">
          <strong>还没有分析会话</strong>
          <p>输入一个经营问题作为标题，创建你的第一条会话。</p>
        </div>
      )}

      {conversations.data && conversations.data.length > 0 && (
        <div className="workspace-body">
          <ul className="conversation-list">
            {conversations.data.map((conversation) => (
              <li
                className={conversation.id === selectedConversationId ? "selected" : undefined}
                key={conversation.id}
              >
                {editingConversationId === conversation.id ? (
                  <form
                    className="rename-form"
                    onSubmit={(event) => handleRenameSubmit(event, conversation.id)}
                  >
                    <input
                      aria-label="新的会话标题"
                      value={editingTitle}
                      maxLength={200}
                      onChange={(event) => setEditingTitle(event.target.value)}
                    />
                    <button type="submit" disabled={!editingTitle.trim()}>
                      保存
                    </button>
                    <button type="button" onClick={() => setEditingConversationId(null)}>
                      取消
                    </button>
                  </form>
                ) : (
                  <button
                    className="conversation-select"
                    type="button"
                    onClick={() => setSelectedConversationId(conversation.id)}
                  >
                    <strong>{conversation.title}</strong>
                    <span>{new Date(conversation.created_at).toLocaleString("zh-CN")}</span>
                  </button>
                )}
                <div className="conversation-actions">
                  <span className="status-pill">
                    {conversation.status === "active" ? "进行中" : "已归档"}
                  </span>
                  <button
                    type="button"
                    onClick={() => beginRename(conversation.id, conversation.title)}
                  >
                    重命名
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      updateConversationMutation.mutate({
                        conversationId: conversation.id,
                        status: conversation.status === "active" ? "archived" : "active",
                      })
                    }
                  >
                    {conversation.status === "active" ? "归档" : "恢复"}
                  </button>
                  <button
                    className="danger-action"
                    type="button"
                    onClick={() => handleDelete(conversation.id, conversation.title)}
                  >
                    删除
                  </button>
                </div>
              </li>
            ))}
          </ul>

          <div className="message-panel">
            {selectedConversation ? (
              <>
                <div className="message-panel-heading">
                  <span className="eyebrow">当前会话</span>
                  <h3>{selectedConversation.title}</h3>
                </div>

                {messages.isPending && <p className="muted">正在读取消息……</p>}
                {messages.isError && <p className="error">消息读取失败，请稍后重试。</p>}
                {messages.data?.length === 0 && (
                  <p className="muted">还没有消息，输入第一个经营问题吧。</p>
                )}
                {messages.data && messages.data.length > 0 && (
                  <ol className="message-list">
                    {messages.data.map((message) => (
                      <li key={message.id}>
                        <span>{message.role === "user" ? "你" : "InsightTrace"}</span>
                        <p>{message.content}</p>
                      </li>
                    ))}
                  </ol>
                )}

                <TaskPanel
                  key={selectedConversation.id}
                  conversationId={selectedConversation.id}
                  isArchived={selectedConversation.status === "archived"}
                />
                <AttachmentPanel
                  conversationId={selectedConversation.id}
                  isArchived={selectedConversation.status === "archived"}
                />
              </>
            ) : (
              <div className="message-placeholder">
                <strong>选择一条会话</strong>
                <p>点击左侧会话，查看并保存它的消息。</p>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
