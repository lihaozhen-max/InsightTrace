import { FormEvent, useEffect, useMemo, useState } from "react";
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

type ConversationFilter = "all" | "active" | "archived";

function formatConversationTime(value: string | null): string {
  if (!value) return "还没有消息";
  return new Date(value).toLocaleString("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ConversationWorkspace() {
  const [title, setTitle] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<ConversationFilter>("all");
  const [isCreating, setIsCreating] = useState(false);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [editingConversationId, setEditingConversationId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const queryClient = useQueryClient();
  const conversations = useQuery({ queryKey: ["conversations"], queryFn: listConversations });
  const messages = useQuery({
    queryKey: ["messages", selectedConversationId],
    queryFn: () => listMessages(selectedConversationId!),
    enabled: selectedConversationId !== null,
  });
  const createConversationMutation = useMutation({
    mutationFn: createConversation,
    onSuccess: async (conversation) => {
      setTitle("");
      setIsCreating(false);
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
      if (selectedConversationId === conversationId) setSelectedConversationId(null);
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  useEffect(() => {
    if (!selectedConversationId && conversations.data?.length) {
      setSelectedConversationId(conversations.data[0].id);
    }
  }, [conversations.data, selectedConversationId]);

  const filteredConversations = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase();
    return (conversations.data ?? []).filter((conversation) => {
      const matchesFilter = filter === "all" || conversation.status === filter;
      const matchesSearch =
        !normalizedSearch || conversation.title.toLocaleLowerCase().includes(normalizedSearch);
      return matchesFilter && matchesSearch;
    });
  }, [conversations.data, filter, search]);

  function handleConversationSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedTitle = title.trim();
    if (normalizedTitle) createConversationMutation.mutate(normalizedTitle);
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
    if (window.confirm(`确定删除“${conversationTitle}”吗？该会话中的消息也会一起删除。`)) {
      deleteConversationMutation.mutate(conversationId);
    }
  }

  const selectedConversation = conversations.data?.find(
    (conversation) => conversation.id === selectedConversationId,
  );

  return (
    <section className="workspace" aria-labelledby="workspace-title">
      <header className="workspace-heading">
        <div>
          <span className="workspace-kicker">Insight workspace</span>
          <h1 id="workspace-title">分析工作台</h1>
        </div>
        <div className="workspace-summary">
          <span><i className="summary-dot" />系统就绪</span>
          <span>{conversations.data?.length ?? 0} 个会话</span>
          <span>演示数据模式</span>
        </div>
      </header>

      <div className="chat-layout">
        <aside className="conversation-sidebar" aria-label="分析会话">
          <div className="sidebar-heading">
            <div>
              <span className="section-label">工作区</span>
              <h2>我的分析会话</h2>
            </div>
            <button
              className="icon-button create-button"
              type="button"
              aria-label="新建会话"
              title="新建会话"
              onClick={() => setIsCreating((value) => !value)}
            >
              +
            </button>
          </div>

          {isCreating && (
            <form className="conversation-form" onSubmit={handleConversationSubmit}>
              <label htmlFor="conversation-title">新会话标题</label>
              <input
                id="conversation-title"
                value={title}
                maxLength={200}
                autoFocus
                placeholder="例如：诊断本月转化下降"
                onChange={(event) => setTitle(event.target.value)}
              />
              <div>
                <button type="button" onClick={() => setIsCreating(false)}>取消</button>
                <button
                  className="primary-button"
                  type="submit"
                  disabled={!title.trim() || createConversationMutation.isPending}
                >
                  {createConversationMutation.isPending ? "创建中…" : "创建"}
                </button>
              </div>
            </form>
          )}

          <label className="conversation-search">
            <span aria-hidden="true">⌕</span>
            <input
              type="search"
              value={search}
              placeholder="搜索会话"
              aria-label="搜索会话"
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>

          <div className="conversation-filters" aria-label="会话筛选">
            {(["all", "active", "archived"] as const).map((value) => (
              <button
                className={filter === value ? "active" : undefined}
                type="button"
                key={value}
                onClick={() => setFilter(value)}
              >
                {{ all: "全部", active: "进行中", archived: "已归档" }[value]}
              </button>
            ))}
          </div>

          {conversations.isPending && <p className="sidebar-state">正在读取会话……</p>}
          {conversations.isError && <p className="error sidebar-state">会话列表读取失败。</p>}
          {createConversationMutation.isError && <p className="error sidebar-state">创建失败，请重试。</p>}

          <ul className="conversation-list">
            {filteredConversations.map((conversation) => (
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
                      autoFocus
                      onChange={(event) => setEditingTitle(event.target.value)}
                    />
                    <button type="submit" disabled={!editingTitle.trim()}>保存</button>
                    <button type="button" onClick={() => setEditingConversationId(null)}>取消</button>
                  </form>
                ) : (
                  <>
                    <button
                      className="conversation-select"
                      type="button"
                      onClick={() => setSelectedConversationId(conversation.id)}
                    >
                      <span className="conversation-icon" aria-hidden="true">◇</span>
                      <span className="conversation-copy">
                        <strong>{conversation.title}</strong>
                        <small>{formatConversationTime(conversation.last_message_at ?? conversation.created_at)}</small>
                      </span>
                      {conversation.status === "active" && <i className="unread-dot" />}
                    </button>
                    <details className="conversation-menu">
                      <summary aria-label={`管理会话 ${conversation.title}`}>•••</summary>
                      <div>
                        <button type="button" onClick={() => beginRename(conversation.id, conversation.title)}>重命名</button>
                        <button
                          type="button"
                          onClick={() => updateConversationMutation.mutate({
                            conversationId: conversation.id,
                            status: conversation.status === "active" ? "archived" : "active",
                          })}
                        >
                          {conversation.status === "active" ? "归档" : "恢复"}
                        </button>
                        <button className="danger-action" type="button" onClick={() => handleDelete(conversation.id, conversation.title)}>删除</button>
                      </div>
                    </details>
                  </>
                )}
              </li>
            ))}
          </ul>

          {!conversations.isPending && filteredConversations.length === 0 && (
            <div className="sidebar-empty">
              <span>◌</span>
              <strong>{conversations.data?.length ? "没有匹配的会话" : "还没有会话"}</strong>
              <p>新建一个会话，开始第一次经营分析。</p>
            </div>
          )}
        </aside>

        <div className="chat-main" aria-label="分析对话">
          {selectedConversation ? (
            <>
              <header className="chat-header">
                <div>
                  <span className={`conversation-state ${selectedConversation.status}`}>
                    {selectedConversation.status === "active" ? "进行中" : "已归档"}
                  </span>
                  <h2>{selectedConversation.title}</h2>
                </div>
                <div className="chat-header-meta">
                  <span>会话数据已保存</span>
                  <span className="secure-badge">只读安全模式</span>
                </div>
              </header>

              <div className="message-scroll">
                {messages.isPending && <p className="loading-line">正在读取历史消息……</p>}
                {messages.isError && <p className="error">消息读取失败，请稍后重试。</p>}
                {messages.data?.length === 0 && (
                  <div className="conversation-welcome">
                    <span className="assistant-avatar">IT</span>
                    <div>
                      <strong>准备好了，我们开始分析吧</strong>
                      <p>
                        <span>还没有消息，输入第一个经营问题吧。</span>
                        我会读取可用数据，计算指标，并为结论标注证据。
                      </p>
                    </div>
                  </div>
                )}
                {messages.data && messages.data.length > 0 && (
                  <ol className="message-list">
                    {messages.data.map((message) => {
                      const isUser = message.role === "user";
                      return (
                        <li className={isUser ? "user-message" : "assistant-message"} key={message.id}>
                          <span className="message-avatar">{isUser ? "你" : "IT"}</span>
                          <div className="message-content">
                            <div className="message-meta">
                              <strong>{isUser ? "你" : "InsightTrace"}</strong>
                              <time>{new Date(message.created_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</time>
                            </div>
                            <p>{message.content}</p>
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                )}

                <TaskPanel
                  key={selectedConversation.id}
                  conversationId={selectedConversation.id}
                  isArchived={selectedConversation.status === "archived"}
                />
              </div>
            </>
          ) : (
            <div className="message-placeholder">
              <span className="placeholder-mark">IT</span>
              <strong>选择一条分析会话</strong>
              <p>会话中的问题、证据、结果和附件都会在这里统一展示。</p>
            </div>
          )}
        </div>

        <aside className="context-sidebar" aria-label="会话数据与说明">
          {selectedConversation ? (
            <>
              <div className="context-intro">
                <span className="section-label">Data context</span>
                <h3>数据与附件</h3>
                <p>上传本轮分析需要的数据文件，解析完成后即可在对话中使用。</p>
              </div>
              <AttachmentPanel
                conversationId={selectedConversation.id}
                isArchived={selectedConversation.status === "archived"}
              />
              <div className="guardrail-card">
                <span aria-hidden="true">✦</span>
                <div>
                  <strong>分析安全边界</strong>
                  <p>仅执行白名单只读查询，结论会区分事实、相关性与待验证推断。</p>
                </div>
              </div>
            </>
          ) : (
            <div className="context-placeholder">选择会话后查看数据源。</div>
          )}
        </aside>
      </div>
    </section>
  );
}
