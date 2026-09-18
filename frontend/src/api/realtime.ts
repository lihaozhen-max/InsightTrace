export interface WebSocketTokenResponse {
  token: string;
  conversation_id: string;
  expires_at: string;
  websocket_path: string;
}

export interface RealtimeEvent {
  event_id: string;
  event_type:
    | "connected"
    | "message_start"
    | "message_delta"
    | "tool_start"
    | "tool_finish"
    | "report_audit"
    | "task_status"
    | "result_ready"
    | "error"
    | "done";
  task_id: string | null;
  conversation_id: string;
  seq_no: number;
  timestamp: string;
  payload: Record<string, unknown>;
}

export async function issueWebSocketToken(
  conversationId: string,
): Promise<WebSocketTokenResponse> {
  const response = await fetch("/api/chat/ws-token", {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId }),
  });
  if (!response.ok) throw new Error("无法建立实时连接");
  return (await response.json()) as WebSocketTokenResponse;
}
