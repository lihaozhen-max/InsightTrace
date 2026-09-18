import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getAdminConfigs,
  getAdminHealth,
  getAdminTasks,
  reloadAdminConfigs,
} from "../api/admin";

const statusLabels = {
  queued: "排队中",
  running: "分析中",
  success: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

export function AdminPanel() {
  const queryClient = useQueryClient();
  const configs = useQuery({ queryKey: ["admin-configs"], queryFn: getAdminConfigs });
  const health = useQuery({ queryKey: ["admin-health"], queryFn: getAdminHealth });
  const tasks = useQuery({ queryKey: ["admin-tasks"], queryFn: getAdminTasks });
  const reload = useMutation({
    mutationFn: reloadAdminConfigs,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["admin-configs"] }),
        queryClient.invalidateQueries({ queryKey: ["admin-health"] }),
      ]);
    },
  });

  return (
    <section className="admin-panel" aria-labelledby="admin-title">
      <div className="admin-heading">
        <div>
          <p className="eyebrow">M5 · 运行管理</p>
          <h2 id="admin-title">管理员控制台</h2>
        </div>
        <button type="button" disabled={reload.isPending} onClick={() => reload.mutate()}>
          {reload.isPending ? "重载中…" : "重新加载配置"}
        </button>
      </div>

      {(configs.isError || health.isError || tasks.isError || reload.isError) && (
        <p className="error">管理数据暂时无法读取，请稍后重试。</p>
      )}

      <div className="admin-grid">
        <article>
          <h3>运行健康</h3>
          {health.data && (
            <dl>
              <div><dt>整体</dt><dd>{health.data.status === "healthy" ? "正常" : "需检查"}</dd></div>
              <div><dt>数据库</dt><dd>{health.data.database === "ok" ? "正常" : "异常"}</dd></div>
              <div><dt>存储</dt><dd>{health.data.storage === "ok" ? "正常" : "异常"}</dd></div>
              <div><dt>分析模式</dt><dd>{health.data.analysis_mode}</dd></div>
              <div><dt>模型</dt><dd>{health.data.model_configured ? "已配置" : "演示模式"}</dd></div>
            </dl>
          )}
        </article>
        <article>
          <h3>非敏感配置</h3>
          <dl>
            {configs.data?.items.map((item) => (
              <div key={item.key}><dt>{item.key}</dt><dd>{String(item.value ?? "未配置")}</dd></div>
            ))}
          </dl>
        </article>
      </div>

      <article className="admin-task-list">
        <h3>最近任务日志</h3>
        {tasks.data?.length === 0 && <p className="muted">还没有分析任务。</p>}
        <ol>
          {tasks.data?.map((task) => (
            <li key={task.id}>
              <span className={`task-status ${task.task_status}`}>
                {statusLabels[task.task_status]}
              </span>
              <div>
                <strong>{task.user_display_name} · {task.last_log_type ?? "无日志"}</strong>
                <p>{task.error_message ?? task.last_log_content ?? "等待任务日志"}</p>
              </div>
              <time>{new Date(task.created_at).toLocaleString("zh-CN")}</time>
            </li>
          ))}
        </ol>
      </article>
    </section>
  );
}
