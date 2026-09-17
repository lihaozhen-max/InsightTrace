export type ConversationStatus = "active" | "archived" | "deleted";

export interface Conversation {
  id: string;
  title: string;
  status: ConversationStatus;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
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
