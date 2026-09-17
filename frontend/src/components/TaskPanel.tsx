import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelTask,
  createTask,
  listTaskLogs,
  listTasks,
  retryTask,
  TaskStatus,
  TaskLog,
} from "../api/tasks";
import { issueWebSocketToken, RealtimeEvent } from "../api/realtime";

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

const stepLabels: Record<string, string> = {
  preparing_context: "准备分析上下文",
  inspecting_sources: "检查数据源",
  querying_data: "查询数据",
  calculating_metrics: "计算指标",
  building_evidence: "整理证据",
  generating_conclusion: "生成结论",
  saving_result: "保存结果",
};

function taskLogText(log: TaskLog): string {
  if (!["message_start", "message_delta", "tool_start", "tool_finish", "result_ready"].includes(log.log_type)) {
    return log.log_content;
  }
  try {
    const payload = JSON.parse(log.log_content) as Record<string, unknown>;
    if (log.log_type === "message_start") return "开始生成分析说明";
    if (log.log_type === "message_delta") return String(payload.delta_text ?? "生成分析说明");
    if (log.log_type === "tool_start") return `开始使用工具：${String(payload.summary ?? payload.tool_name)}`;
    if (log.log_type === "tool_finish") return String(payload.result_summary ?? "工具执行完成");
    return "分析结果已经保存";
  } catch {
    return log.log_content;
  }
}

export function TaskPanel({ conversationId, isArchived }: TaskPanelProps) {
  const [inputText, setInputText] = useState("");
  const [realtimeStatus, setRealtimeStatus] = useState<"idle" | "connecting" | "connected">("idle");
  const [liveUpdates, setLiveUpdates] = useState<string[]>([]);
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

  useEffect(() => {
    setLiveUpdates([]);
  }, [latestTask?.id]);

  useEffect(() => {
    if (!latestTask || !["queued", "running"].includes(latestTask.task_status)) {
      setRealtimeStatus("idle");
      return;
    }

    let socket: WebSocket | undefined;
    let disposed = false;
    setRealtimeStatus("connecting");
    void issueWebSocketToken(conversationId)
      .then((issued) => {
        if (disposed) return;
        const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
        const query = new URLSearchParams({
          websocket_token: issued.token,
          conversation_id: conversationId,
        });
        socket = new WebSocket(`${scheme}//${window.location.host}${issued.websocket_path}?${query}`);
        socket.onmessage = (message) => {
          const event = JSON.parse(message.data as string) as RealtimeEvent;
          if (event.event_type === "connected") setRealtimeStatus("connected");
          if (event.event_type === "message_delta") {
            setLiveUpdates((items) => [...items, String(event.payload.delta_text ?? "")]);
          }
          if (event.event_type === "tool_start") {
            setLiveUpdates((items) => [
              ...items,
              `正在执行：${String(event.payload.summary ?? event.payload.tool_name)}`,
            ]);
          }
          if (event.event_type === "tool_finish") {
            setLiveUpdates((items) => [
              ...items,
              String(event.payload.result_summary ?? "工具执行完成"),
            ]);
          }
          if (event.event_type === "result_ready") {
            setLiveUpdates((items) => [...items, "结构化分析结果已经保存"]);
          }
          if (["task_status", "error", "done"].includes(event.event_type)) {
            void queryClient.invalidateQueries({ queryKey: ["tasks", conversationId] });
            void queryClient.invalidateQueries({ queryKey: ["task-logs", latestTask.id] });
          }
          if (event.event_type === "done") void refreshTaskData();
        };
        socket.onclose = () => {
          if (!disposed) setRealtimeStatus("idle");
        };
      })
      .catch(() => {
        if (!disposed) setRealtimeStatus("idle");
      });

    return () => {
      disposed = true;
      socket?.close();
    };
  }, [conversationId, latestTask?.id, queryClient]);

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
            {latestTask.current_step && (
              <span className="task-current-step">
                {stepLabels[latestTask.current_step] ?? latestTask.current_step}
              </span>
            )}
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
      {latestTask?.task_status === "queued" && <p className="task-note">任务已进入执行队列。</p>}
      {hasActiveTask && (
        <p className={`realtime-status ${realtimeStatus}`}>
          {realtimeStatus === "connected" ? "实时连接已建立" : "正在建立实时连接…"}
        </p>
      )}
      {liveUpdates.length > 0 && (
        <div className="live-analysis" aria-live="polite">
          <strong>实时分析进度</strong>
          <ol>
            {liveUpdates.map((update, index) => <li key={`${index}-${update}`}>{update}</li>)}
          </ol>
        </div>
      )}
      {(cancel.isError || retry.isError) && <p className="error">任务操作失败，请稍后重试。</p>}
      {logs.data && logs.data.length > 0 && (
        <ol className="task-log-list">
          {logs.data.map((log) => <li key={log.id}>{taskLogText(log)}</li>)}
        </ol>
      )}
    </section>
  );
}
