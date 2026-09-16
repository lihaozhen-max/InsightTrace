import { useQuery } from "@tanstack/react-query";

import { getReadiness } from "./api/health";

const milestones = [
  "模拟 OAuth 登录与角色识别",
  "会话、消息和附件管理",
  "WebSocket 实时分析任务",
  "商品目录优化黄金路径",
];

export function App() {
  const readiness = useQuery({
    queryKey: ["readiness"],
    queryFn: getReadiness,
    refetchInterval: 15_000,
  });

  const isReady = readiness.data?.status === "ready";

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="InsightTrace 首页">
          <span className="brand-mark">IT</span>
          <span>InsightTrace</span>
        </a>
        <span className="version">MVP v1 · 基础骨架</span>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">经营分析归因系统</p>
          <h1>让经营结论有数据、有证据、可追溯</h1>
          <p className="lead">
            当前基础服务已经就位。下一阶段将沿着商品目录优化黄金路径，逐步接入会话、任务和结构化分析结果。
          </p>
        </div>

        <article className="status-card" aria-live="polite">
          <div className="status-title">
            <span className={`status-dot ${isReady ? "ready" : "pending"}`} />
            <strong>系统状态</strong>
          </div>

          {readiness.isPending && <p>正在检查后端服务……</p>}
          {readiness.isError && <p className="error">后端暂不可用，请确认服务已经启动。</p>}
          {readiness.data && (
            <dl>
              <div>
                <dt>API</dt>
                <dd>{isReady ? "已就绪" : "未就绪"}</dd>
              </div>
              <div>
                <dt>PostgreSQL</dt>
                <dd>{readiness.data.components.database.status === "ok" ? "已连接" : "连接失败"}</dd>
              </div>
              <div>
                <dt>文件存储</dt>
                <dd>{readiness.data.components.storage.status === "ok" ? "可用" : "不可用"}</dd>
              </div>
            </dl>
          )}
        </article>
      </section>

      <section className="next-steps" aria-labelledby="next-steps-title">
        <div>
          <p className="eyebrow">下一阶段</p>
          <h2 id="next-steps-title">从骨架走向第一条完整分析链路</h2>
        </div>
        <ol>
          {milestones.map((milestone, index) => (
            <li key={milestone}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              {milestone}
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
