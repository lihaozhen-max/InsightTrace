export type ConversationStatus = "active" | "archived" | "deleted";

export interface Conversation {
  id: string;
  title: string;
  status: ConversationStatus;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system" | "tool";
  message_type: "text" | "status" | "tool" | "error";
  content: string;
  seq_no: number;
  created_at: string;
}

export async function listConversations(): Promise<Conversation[]> {
  const response = await fetch("/api/conversations", {
    credentials: "include",
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new Error("无法读取会话列表");
  }

  return (await response.json()) as Conversation[];
}

export async function createConversation(title: string): Promise<Conversation> {
  const response = await fetch("/api/conversations", {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ title }),
  });

  if (!response.ok) {
    throw new Error("创建会话失败");
  }

  return (await response.json()) as Conversation;
}

export async function updateConversation({
  conversationId,
  title,
  status,
}: {
  conversationId: string;
  title?: string;
  status?: "active" | "archived";
}): Promise<Conversation> {
  const response = await fetch(`/api/conversations/${conversationId}`, {
    method: "PATCH",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ title, status }),
  });

  if (!response.ok) {
    throw new Error("更新会话失败");
  }

  return (await response.json()) as Conversation;
}

export async function deleteConversation(conversationId: string): Promise<void> {
  const response = await fetch(`/api/conversations/${conversationId}`, {
    method: "DELETE",
    credentials: "include",
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new Error("删除会话失败");
  }
}

export async function listMessages(conversationId: string): Promise<Message[]> {
  const response = await fetch(`/api/conversations/${conversationId}/messages`, {
    credentials: "include",
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new Error("无法读取消息记录");
  }

  return (await response.json()) as Message[];
}

export async function createMessage({
  conversationId,
  content,
}: {
  conversationId: string;
  content: string;
}): Promise<Message> {
  const response = await fetch(`/api/conversations/${conversationId}/messages`, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ content }),
  });

  if (!response.ok) {
    throw new Error("消息发送失败");
  }

  return (await response.json()) as Message;
}
