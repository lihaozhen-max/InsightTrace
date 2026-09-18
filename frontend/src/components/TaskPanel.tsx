import { FormEvent, KeyboardEvent, useEffect, useState } from "react";
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
import { listAttachments } from "../api/attachments";
import { issueWebSocketToken, RealtimeEvent } from "../api/realtime";
import { ResultPanel } from "./ResultPanel";

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

const quickPrompts = [
  "为什么本月商品目录转化率下降？",
  "为什么本周访问到下单的转化率下降？",
  "哪些渠道和设备对结果影响最大？",
];

export function taskLogText(log: TaskLog): string {
  if (!["message_start", "message_delta", "tool_start", "tool_finish", "report_audit", "result_ready"].includes(log.log_type)) {
    return log.log_content;
  }
  try {
    const payload = JSON.parse(log.log_content) as Record<string, unknown>;
    if (log.log_type === "message_start") return "开始生成分析说明";
    if (log.log_type === "message_delta") return String(payload.delta_text ?? "生成分析说明");
    if (log.log_type === "tool_start") return `开始使用工具：${String(payload.summary ?? payload.tool_name)}`;
    if (log.log_type === "tool_finish") return String(payload.result_summary ?? "工具执行完成");
    if (log.log_type === "report_audit") {
      const result = payload.result as Record<string, unknown> | undefined;
      return result?.model_output_accepted === false
        ? "报告审校未通过，已安全回退为确定性结论"
        : "报告已通过数值溯源和因果边界审校";
    }
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
      query.state.data?.some((task) => ["queued", "running"].includes(task.task_status)) ? 2_000 : false,
  });
  const attachments = useQuery({
    queryKey: ["attachments", conversationId],
    queryFn: () => listAttachments(conversationId),
  });
  const readyAttachmentIds = (attachments.data ?? [])
    .filter((attachment) => attachment.parse_status === "success")
    .map((attachment) => attachment.id);
  let composerHint = "Enter 发送 · Shift + Enter 换行";
  if (attachments.isPending) composerHint = "正在读取附件……";
  if (attachments.isError) composerHint = "附件状态读取失败";
  if (readyAttachmentIds.length > 0) {
    composerHint = `本轮将使用 ${readyAttachmentIds.length} 个已解析附件`;
  }
  const latestTask = tasks.data?.[0];
  const logs = useQuery({
    queryKey: ["task-logs", latestTask?.id],
    queryFn: () => listTaskLogs(latestTask!.id),
    enabled: latestTask !== undefined,
    refetchInterval: latestTask && ["queued", "running"].includes(latestTask.task_status) ? 2_000 : false,
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
  const hasActiveTask = latestTask && ["queued", "running"].includes(latestTask.task_status);

  function submitQuestion() {
    const normalized = inputText.trim();
    if (
      normalized &&
      !hasActiveTask &&
      !create.isPending &&
      !attachments.isPending &&
      !attachments.isError
    ) {
      create.mutate({
        conversationId,
        inputText: normalized,
        attachmentIds: readyAttachmentIds,
      });
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submitQuestion();
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submitQuestion();
    }
  }

  useEffect(() => setLiveUpdates([]), [latestTask?.id]);

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
            setLiveUpdates((items) => [...items, `正在执行：${String(event.payload.summary ?? event.payload.tool_name)}`]);
          }
          if (event.event_type === "tool_finish") {
            setLiveUpdates((items) => [...items, String(event.payload.result_summary ?? "工具执行完成")]);
          }
          if (event.event_type === "report_audit") {
            const result = event.payload.result as Record<string, unknown> | undefined;
            setLiveUpdates((items) => [
              ...items,
              result?.model_output_accepted === false
                ? "模型表述未通过审校，已使用确定性结论"
                : "报告审校通过",
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
      {latestTask && (
        <div className="analysis-run">
          <div className="analysis-run-heading">
            <span className="assistant-avatar">IT</span>
            <div>
              <div className="message-meta">
                <strong>InsightTrace</strong>
                <span className={`task-status ${latestTask.task_status}`}>{statusLabels[latestTask.task_status]}</span>
              </div>
              <p>{latestTask.current_step ? stepLabels[latestTask.current_step] ?? latestTask.current_step : latestTask.input_text}</p>
            </div>
            {(latestTask.task_status === "queued" || latestTask.task_status === "running") && (
              <button className="secondary-button" type="button" disabled={cancel.isPending} onClick={() => cancel.mutate(latestTask.id)}>
                {cancel.isPending ? "取消中…" : "停止"}
              </button>
            )}
            {(latestTask.task_status === "failed" || latestTask.task_status === "cancelled") && (
              <button className="secondary-button" type="button" disabled={retry.isPending} onClick={() => retry.mutate(latestTask.id)}>
                {retry.isPending ? "创建中…" : "重新分析"}
              </button>
            )}
          </div>

          {hasActiveTask && (
            <div className="realtime-strip">
              <span className={`activity-pulse ${realtimeStatus}`} />
              {realtimeStatus === "connected" ? "实时分析通道已连接" : "正在建立实时连接……"}
            </div>
          )}

          {liveUpdates.length > 0 && (
            <div className="live-analysis" aria-live="polite">
              {liveUpdates.map((update, index) => <p key={`${index}-${update}`}>{update}</p>)}
            </div>
          )}

          {logs.data && logs.data.length > 0 && (
            <details className="process-log">
              <summary>查看执行过程 <span>{logs.data.length} 条</span></summary>
              <ol>{logs.data.map((log) => <li key={log.id}>{taskLogText(log)}</li>)}</ol>
            </details>
          )}

          {(cancel.isError || retry.isError) && <p className="error">任务操作失败，请稍后重试。</p>}
          {latestTask.task_status === "success" && <ResultPanel taskId={latestTask.id} />}
        </div>
      )}

      {isArchived ? (
        <p className="archived-notice">该会话已归档。恢复会话后才能继续追问。</p>
      ) : (
        <div className="composer-area">
          {!latestTask && (
            <div className="quick-prompts">
              {quickPrompts.map((prompt) => (
                <button type="button" key={prompt} onClick={() => setInputText(prompt)}>{prompt}</button>
              ))}
            </div>
          )}
          <form className="message-form" onSubmit={handleSubmit}>
            <label className="sr-only" id="analysis-input-title" htmlFor="analysis-input">输入经营问题</label>
            <textarea
              id="analysis-input"
              value={inputText}
              maxLength={10_000}
              rows={3}
              placeholder="输入你想追问的经营问题……"
              onKeyDown={handleComposerKeyDown}
              onChange={(event) => setInputText(event.target.value)}
            />
            <div className="composer-footer">
              <span>{composerHint}</span>
              <button
                type="submit"
                disabled={
                  !inputText.trim() ||
                  create.isPending ||
                  Boolean(hasActiveTask) ||
                  attachments.isPending ||
                  attachments.isError
                }
              >
                <span>{create.isPending ? "发送中" : hasActiveTask ? "分析中" : "发送"}</span>
                <b aria-hidden="true">↑</b>
              </button>
            </div>
          </form>
          {create.isError && <p className="error composer-error">任务创建失败，请稍后重试。</p>}
        </div>
      )}
    </section>
  );
}
