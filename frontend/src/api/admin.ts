export interface AdminConfigItem {
  key: string;
  value: string | number | boolean | null;
  group: string;
}

export interface AdminConfigResponse {
  items: AdminConfigItem[];
  reloaded_at: string | null;
}

export interface AdminHealth {
  status: "healthy" | "degraded";
  database: "ok" | "error";
  storage: "ok" | "error";
  analysis_mode: string;
  model_configured: boolean;
}

export interface AdminTaskSummary {
  id: string;
  user_display_name: string;
  task_status: "queued" | "running" | "success" | "failed" | "cancelled";
  current_step: string | null;
  error_code: string | null;
  error_message: string | null;
  last_log_type: string | null;
  last_log_content: string | null;
  created_at: string;
  finished_at: string | null;
}

async function readJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    credentials: "include",
    headers: { Accept: "application/json", ...init?.headers },
  });
  if (!response.ok) throw new Error("管理员数据读取失败");
  return (await response.json()) as T;
}

export const getAdminConfigs = () => readJson<AdminConfigResponse>("/api/admin/configs");
export const getAdminHealth = () => readJson<AdminHealth>("/api/admin/health");
export const getAdminTasks = () => readJson<AdminTaskSummary[]>("/api/admin/tasks");
export const reloadAdminConfigs = () =>
  readJson<AdminConfigResponse>("/api/admin/reload", { method: "POST" });
