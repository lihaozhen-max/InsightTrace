export type TaskStatus = "queued" | "running" | "success" | "failed" | "cancelled";

export interface AnalysisTask {
  id: string;
  conversation_id: string;
  retry_of_task_id: string | null;
  input_text: string;
  input_payload_json: { attachment_ids?: string[]; message_id?: string | null };
  analysis_mode: "demo" | "model";
  task_status: TaskStatus;
  current_step: string | null;
  started_at: string | null;
  finished_at: string | null;
  cancel_requested_at: string | null;
  error_code: string | null;
  error_message: string | null;
  retryable: boolean;
  version: number;
  created_at: string;
}

export interface TaskLog {
  id: string;
  task_id: string;
  sequence_no: number;
  log_level: "debug" | "info" | "warning" | "error";
  log_type: string;
  log_content: string;
  created_at: string;
}

export async function listTasks(conversationId: string): Promise<AnalysisTask[]> {
  const response = await fetch(`/api/conversations/${conversationId}/tasks`, {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error("无法读取分析任务");
  return (await response.json()) as AnalysisTask[];
}

export async function createTask({
  conversationId,
  inputText,
  attachmentIds,
}: {
  conversationId: string;
  inputText: string;
  attachmentIds: string[];
}): Promise<AnalysisTask> {
  const response = await fetch("/api/tasks", {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({
      conversation_id: conversationId,
      input_text: inputText,
      attachment_ids: attachmentIds,
    }),
  });
  if (!response.ok) throw new Error("创建分析任务失败");
  return (await response.json()) as AnalysisTask;
}

async function postTaskAction(taskId: string, action: "cancel" | "retry"): Promise<AnalysisTask> {
  const response = await fetch(`/api/tasks/${taskId}/${action}`, {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`任务${action === "cancel" ? "取消" : "重试"}失败`);
  return (await response.json()) as AnalysisTask;
}

export const cancelTask = (taskId: string) => postTaskAction(taskId, "cancel");
export const retryTask = (taskId: string) => postTaskAction(taskId, "retry");

export async function listTaskLogs(taskId: string): Promise<TaskLog[]> {
  const response = await fetch(`/api/tasks/${taskId}/logs`, {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error("无法读取任务日志");
  return (await response.json()) as TaskLog[];
}
