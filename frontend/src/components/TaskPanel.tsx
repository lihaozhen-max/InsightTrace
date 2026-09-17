import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelTask,
  createTask,
  listTaskLogs,
  listTasks,
  retryTask,
  TaskStatus,
} from "../api/tasks";

interface TaskPanelProps {
  conversationId: string;
  isArchived: boolean;
}

const statusLabels: Record<TaskStatus, string> = {
  queued: "排队中",
  running: "分析中",
  success: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

export function TaskPanel({ conversationId, isArchived }: TaskPanelProps) {
  const [inputText, setInputText] = useState("");
  const queryClient = useQueryClient();
  const tasks = useQuery({
    queryKey: ["tasks", conversationId],
    queryFn: () => listTasks(conversationId),
    refetchInterval: (query) =>
      query.state.data?.some((task) => ["queued", "running"].includes(task.task_status))
        ? 2_000
        : false,
  });
  const latestTask = tasks.data?.[0];
  const logs = useQuery({
    queryKey: ["task-logs", latestTask?.id],
    queryFn: () => listTaskLogs(latestTask!.id),
    enabled: latestTask !== undefined,
    refetchInterval: latestTask && ["queued", "running"].includes(latestTask.task_status)
      ? 2_000
      : false,
  });

  async function refreshTaskData() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["tasks", conversationId] }),
      queryClient.invalidateQueries({ queryKey: ["messages", conversationId] }),
      queryClient.invalidateQueries({ queryKey: ["conversations"] }),
    ]);
  }

  const create = useMutation({
    mutationFn: createTask,
    onSuccess: async () => {
      setInputText("");
      await refreshTaskData();
    },
  });
  const cancel = useMutation({ mutationFn: cancelTask, onSuccess: refreshTaskData });
  const retry = useMutation({ mutationFn: retryTask, onSuccess: refreshTaskData });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = inputText.trim();
    if (normalized) create.mutate({ conversationId, inputText: normalized });
  }

  const hasActiveTask = latestTask && ["queued", "running"].includes(latestTask.task_status);

  return (
    <section className="task-panel" aria-labelledby="analysis-input-title">
      {isArchived ? (
        <p className="archived-notice">该会话已归档。恢复后才能创建分析任务。</p>
      ) : (
        <form className="message-form" onSubmit={handleSubmit}>
          <label id="analysis-input-title" htmlFor="analysis-input">输入经营问题</label>
          <textarea
            id="analysis-input"
            value={inputText}
            maxLength={10_000}
            rows={4}
            placeholder="例如：请帮我分析销量下降可能由哪些指标造成"
            onChange={(event) => setInputText(event.target.value)}
          />
          <button
            type="submit"
            disabled={!inputText.trim() || create.isPending || Boolean(hasActiveTask)}
          >
            {create.isPending ? "正在创建…" : hasActiveTask ? "已有任务进行中" : "开始分析"}
          </button>
          {create.isError && <span className="error">任务创建失败，请稍后重试。</span>}
        </form>
      )}

      {latestTask && (
        <div className="task-status-card">
          <div>
            <span className={`task-status ${latestTask.task_status}`}>
              {statusLabels[latestTask.task_status]}
            </span>
            <strong>{latestTask.input_text}</strong>
          </div>
          {(latestTask.task_status === "queued" || latestTask.task_status === "running") && (
            <button type="button" disabled={cancel.isPending} onClick={() => cancel.mutate(latestTask.id)}>
              {cancel.isPending ? "取消中…" : "取消任务"}
            </button>
          )}
          {(latestTask.task_status === "failed" || latestTask.task_status === "cancelled") && (
            <button type="button" disabled={retry.isPending} onClick={() => retry.mutate(latestTask.id)}>
              {retry.isPending ? "创建中…" : "重新分析"}
            </button>
          )}
        </div>
      )}
      {latestTask?.task_status === "queued" && (
        <p className="task-note">任务已经可靠保存；分析执行器将在 M3 下一阶段接入。</p>
      )}
      {(cancel.isError || retry.isError) && <p className="error">任务操作失败，请稍后重试。</p>}
      {logs.data && logs.data.length > 0 && (
        <ol className="task-log-list">
          {logs.data.map((log) => <li key={log.id}>{log.log_content}</li>)}
        </ol>
      )}
    </section>
  );
}
