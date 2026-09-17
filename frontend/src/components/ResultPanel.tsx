import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { exportResult, getResult, resultDownloadUrl } from "../api/results";

interface ResultPanelProps {
  taskId: string;
}

function metricLabel(metric: Record<string, unknown>): string {
  return String(metric.metric_name ?? metric.name ?? "指标");
}

function metricValue(metric: Record<string, unknown>): string {
  const value = metric.metric_value ?? metric.value ?? "—";
  const unit = metric.metric_unit ?? metric.unit ?? "";
  return `${String(value)}${String(unit)}`;
}

function evidenceText(evidence: Record<string, unknown>): string {
  return String(evidence.evidence_text ?? evidence.summary ?? "已记录证据");
}

export function ResultPanel({ taskId }: ResultPanelProps) {
  const queryClient = useQueryClient();
  const result = useQuery({
    queryKey: ["analysis-result", taskId],
    queryFn: () => getResult(taskId),
  });
  const exportReport = useMutation({
    mutationFn: () => exportResult(taskId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["analysis-result", taskId] });
    },
  });

  if (result.isPending) return <p className="muted">正在读取结构化结果……</p>;
  if (result.isError || !result.data) return <p className="error">结构化结果读取失败。</p>;

  return (
    <section className="result-panel" aria-labelledby="result-title">
      <div className="result-heading">
        <div>
          <span className="eyebrow">六部分结构化结果</span>
          <h4 id="result-title">分析结果</h4>
        </div>
        {result.data.report_available ? (
          <a className="report-action" href={resultDownloadUrl(taskId)}>下载 Markdown</a>
        ) : (
          <button
            className="report-action"
            type="button"
            disabled={exportReport.isPending}
            onClick={() => exportReport.mutate()}
          >
            {exportReport.isPending ? "生成中…" : "生成 Markdown"}
          </button>
        )}
      </div>

      <article><h5>1. 问题定义</h5><p>{result.data.problem_definition}</p></article>
      <article>
        <h5>2. 关键指标</h5>
        <div className="metric-grid">
          {result.data.key_metrics.map((metric, index) => (
            <div className="metric-card" key={`${metricLabel(metric)}-${index}`}>
              <span>{metricLabel(metric)}</span><strong>{metricValue(metric)}</strong>
            </div>
          ))}
        </div>
      </article>
      <article>
        <h5>3. 证据</h5>
        <ol>{result.data.evidence_list.map((item, index) => (
          <li key={String(item.evidence_id ?? index)}>{evidenceText(item)}</li>
        ))}</ol>
      </article>
      <article><h5>4. 结论</h5><p>{result.data.conclusion_text}</p></article>
      <article><h5>5. 缺失数据</h5><p>{result.data.missing_data_text || "无"}</p></article>
      <article>
        <h5>6. 下一步建议</h5>
        <ul>{result.data.next_actions.map((item) => <li key={item}>{item}</li>)}</ul>
      </article>
      {result.data.confidence !== null && (
        <p className="result-confidence">结果置信度：{Math.round(result.data.confidence * 100)}%</p>
      )}
      {exportReport.isError && <p className="error">报告生成失败，请稍后重试。</p>}
    </section>
  );
}
