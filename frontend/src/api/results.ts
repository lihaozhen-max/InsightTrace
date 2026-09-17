export interface AnalysisResult {
  id: string;
  task_id: string;
  conversation_id: string;
  problem_definition: string;
  key_metrics: Array<Record<string, unknown>>;
  evidence_list: Array<Record<string, unknown>>;
  conclusion_text: string;
  missing_data_text: string;
  next_actions: string[];
  result_markdown: string;
  result_version: number;
  generated_by: "demo" | "model";
  confidence: number | null;
  report_available: boolean;
  created_at: string;
  updated_at: string;
}

export interface ResultExport {
  task_id: string;
  file_name: string;
  download_path: string;
}

export async function getResult(taskId: string): Promise<AnalysisResult> {
  const response = await fetch(`/api/results/${taskId}`, {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error("无法读取分析结果");
  return (await response.json()) as AnalysisResult;
}

export async function exportResult(taskId: string): Promise<ResultExport> {
  const response = await fetch(`/api/results/${taskId}/export`, {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error("无法生成 Markdown 报告");
  return (await response.json()) as ResultExport;
}

export const resultDownloadUrl = (taskId: string) => `/api/results/${taskId}/download`;
