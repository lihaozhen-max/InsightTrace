import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getCurrentUser, logout } from "./api/auth";
import { getReadiness } from "./api/health";
import { ConversationWorkspace } from "./components/ConversationWorkspace";
import { AdminPanel } from "./components/AdminPanel";

const milestones = [
  "模拟 OAuth 登录与角色识别",
  "会话、消息和附件管理",
  "WebSocket 实时分析任务",
  "商品目录与客户行为黄金路径",
  "管理配置、运行日志与安全验收",
];

export function App() {
  const queryClient = useQueryClient();
  const user = useQuery({
    queryKey: ["current-user"],
    queryFn: getCurrentUser,
    retry: false,
  });
  const readiness = useQuery({
    queryKey: ["readiness"],
    queryFn: getReadiness,
    refetchInterval: 15_000,
  });

  const isReady = readiness.data?.status === "ready";
  const logoutMutation = useMutation({
    mutationFn: logout,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["current-user"] });
    },
  });

  return (
    <main className={`shell ${user.data ? "authenticated-shell" : "landing-shell"}`}>
      <header className="topbar">
        <a className="brand" href="/" aria-label="InsightTrace 首页">
          <span className="brand-mark">IT</span>
          <span>InsightTrace</span>
        </a>
        <div className="account-area">
          {user.data ? (
            <>
              <span className={`header-health ${isReady ? "ready" : "pending"}`}>
                <i />{isReady ? "服务正常" : "检查服务"}
              </span>
              <span className="user-avatar">{user.data.display_name.slice(0, 1)}</span>
              <span className="user-badge">
                <strong>{user.data.display_name}</strong>
                <small>{user.data.role === "admin" ? "系统管理员" : "分析用户"}</small>
              </span>
              <button
                className="text-button"
                type="button"
                disabled={logoutMutation.isPending}
                onClick={() => logoutMutation.mutate()}
              >
                退出
              </button>
            </>
          ) : (
            <span className="version">MVP v1 · M5 验收版</span>
          )}
        </div>
      </header>

      {!user.data && <section className="hero">
        <div>
          <p className="eyebrow">经营分析归因系统</p>
          <h1>让经营结论有数据、有证据、可追溯</h1>
          {user.isPending ? (
            <p className="lead">正在检查登录状态……</p>
          ) : (
            <>
              <p className="lead">
                使用内置模拟认证中心选择分析用户或管理员身份，体验与真实 OAuth/OIDC 一致的授权和回调流程。
              </p>
              <a className="primary-action" href="/auth/login">
                进入演示授权登录
              </a>
            </>
          )}
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
      </section>}

      {user.data && <ConversationWorkspace />}
      {user.data?.role === "admin" && <AdminPanel />}

      {!user.data && <section className="next-steps" aria-labelledby="next-steps-title">
        <div>
          <p className="eyebrow">下一阶段</p>
          <h2 id="next-steps-title">
            登录后体验结构化分析链路
          </h2>
        </div>
        <ol>
          {milestones.map((milestone, index) => (
            <li key={milestone}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              {milestone}
            </li>
          ))}
        </ol>
      </section>}
    </main>
  );
}
