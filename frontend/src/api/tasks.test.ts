import { describe, expect, it, vi } from "vitest";

import { createTask } from "./tasks";


describe("createTask", () => {
  it("submits selected attachments and lets the server choose analysis mode", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);

    await createTask({
      conversationId: "conversation-1",
      inputText: "分析附件",
      attachmentIds: ["attachment-1", "attachment-2"],
    });

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(options.body))).toEqual({
      conversation_id: "conversation-1",
      input_text: "分析附件",
      attachment_ids: ["attachment-1", "attachment-2"],
    });
  });
});
