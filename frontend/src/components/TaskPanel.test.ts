import { describe, expect, it } from "vitest";

import { taskLogText } from "./TaskPanel";


describe("taskLogText", () => {
  it("explains when report auditing falls back to deterministic output", () => {
    const text = taskLogText({
      id: "log-1",
      task_id: "task-1",
      sequence_no: 1,
      log_level: "info",
      log_type: "report_audit",
      log_content: JSON.stringify({ result: { model_output_accepted: false } }),
      created_at: "2026-09-18T00:00:00Z",
    });

    expect(text).toContain("安全回退");
  });
});
