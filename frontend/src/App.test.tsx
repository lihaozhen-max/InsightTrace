import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = input.toString();
        if (url.endsWith("/api/me")) {
          return {
            ok: false,
            status: 401,
            json: async () => ({ error: { code: "UNAUTHENTICATED" } }),
          };
        }

        return {
          ok: true,
          status: 200,
          json: async () => ({
            status: "ready",
            service: "InsightTrace",
            environment: "test",
            components: {
              database: { status: "ok" },
              storage: { status: "ok" },
            },
          }),
        };
      }),
    );
  });

  it("renders the product heading", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    );

    expect(screen.getByRole("heading", { name: /让经营结论有数据/ })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "进入演示授权登录" })).toHaveAttribute(
      "href",
      "/auth/login",
    );
    expect(await screen.findByText("已连接")).toBeInTheDocument();
  });

  it("shows the signed-in user's conversation workspace", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = input.toString();
        if (url.endsWith("/api/me")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              id: "user-1",
              username: "demo.analyst",
              display_name: "演示分析用户",
              role: "analyst",
              status: "active",
              created_at: "2026-09-17T00:00:00Z",
            }),
          };
        }

        if (url.endsWith("/api/conversations")) {
          return {
            ok: true,
            status: 200,
            json: async () => [
              {
                id: "conversation-1",
                title: "分析本月商品转化下降原因",
                status: "active",
                last_message_at: null,
                created_at: "2026-09-17T00:00:00Z",
                updated_at: "2026-09-17T00:00:00Z",
              },
            ],
          };
        }

        if (url.endsWith("/api/conversations/conversation-1/messages")) {
          return {
            ok: true,
            status: 200,
            json: async () => [],
          };
        }

        if (url.endsWith("/api/conversations/conversation-1/attachments")) {
          return {
            ok: true,
            status: 200,
            json: async () => [
              {
                id: "attachment-1",
                conversation_id: "conversation-1",
                file_name: "broken.json",
                file_type: "application/json",
                file_size: 12,
                sha256: "hash",
                parse_status: "failed",
                parse_error: "JSON 格式错误：第 1 行第 12 列",
                created_at: "2026-09-17T00:00:00Z",
              },
            ],
          };
        }

        if (url.endsWith("/api/conversations/conversation-1/tasks")) {
          return {
            ok: true,
            status: 200,
            json: async () => [],
          };
        }

        return {
          ok: true,
          status: 200,
          json: async () => ({
            status: "ready",
            service: "InsightTrace",
            environment: "test",
            components: {
              database: { status: "ok" },
              storage: { status: "ok" },
            },
          }),
        };
      }),
    );

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("heading", { name: "我的分析会话" })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /分析本月商品转化下降原因/ }));
    expect(await screen.findByText("还没有消息，输入第一个经营问题吧。")).toBeInTheDocument();
    expect(await screen.findByText("broken.json")).toBeInTheDocument();
    expect(screen.getByText("JSON 格式错误：第 1 行第 12 列")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新解析" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始分析" })).toBeInTheDocument();
  });
});
