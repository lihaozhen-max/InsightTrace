import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: "ready",
          service: "InsightTrace",
          environment: "test",
          components: {
            database: { status: "ok" },
            storage: { status: "ok" },
          },
        }),
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
    expect(await screen.findByText("已连接")).toBeInTheDocument();
  });
});
