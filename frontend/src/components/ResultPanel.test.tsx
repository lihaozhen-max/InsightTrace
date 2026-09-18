import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ResultPanel } from "./ResultPanel";

describe("ResultPanel", () => {
  it("shows formulas, evidence levels, sources, samples, and limitations", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          id: "result-1",
          task_id: "task-1",
          conversation_id: "conversation-1",
          problem_definition: "为什么转化率下降？",
          key_metrics: [
            {
              metric_name: "整体下单转化率",
              metric_value: 4.92,
              metric_unit: "%",
              formula: "SUM(下单量) / SUM(点击量)",
              source_name: "funnel.xlsx",
              sheet_name: "商品漏斗",
            },
          ],
          evidence_list: [
            {
              evidence_id: "E-001",
              evidence_text: "点击到加购环节贡献了主要降幅。",
              fact_level: "calculation",
              source_name: "funnel.xlsx",
              sheet_name: "商品漏斗",
              formula: "two-factor Shapley decomposition",
              sample_size: 60,
              limitations: "缺少促销数据",
            },
          ],
          conclusion_text: "下降主要发生在点击到加购环节。",
          missing_data_text: "缺少促销数据。",
          next_actions: ["复核库存日志"],
          result_markdown: "# report",
          result_version: 1,
          generated_by: "model",
          confidence: 0.9,
          report_available: false,
          created_at: "2026-09-18T00:00:00Z",
          updated_at: "2026-09-18T00:00:00Z",
        }),
      }),
    );
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ResultPanel taskId="task-1" />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("4.92%")).toBeInTheDocument();
    expect(screen.getByText("SUM(下单量) / SUM(点击量)")).toBeInTheDocument();
    expect(screen.getByText("确定性计算")).toBeInTheDocument();
    expect(screen.getAllByText("funnel.xlsx / 商品漏斗")).toHaveLength(2);
    expect(screen.getByText("样本量：60")).toBeInTheDocument();
    expect(screen.getByText("限制：缺少促销数据")).toBeInTheDocument();
  });
});
