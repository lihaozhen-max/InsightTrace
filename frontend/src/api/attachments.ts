export type AttachmentParseStatus = "pending" | "parsing" | "success" | "failed";

export interface Attachment {
  id: string;
  conversation_id: string;
  file_name: string;
  file_type: string;
  file_size: number;
  sha256: string;
  parse_status: AttachmentParseStatus;
  parse_error: string | null;
  created_at: string;
}

export async function listAttachments(conversationId: string): Promise<Attachment[]> {
  const response = await fetch(`/api/conversations/${conversationId}/attachments`, {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error("无法读取附件列表");
  }
  return (await response.json()) as Attachment[];
}

export async function uploadAttachment({
  conversationId,
  file,
}: {
  conversationId: string;
  file: File;
}): Promise<Attachment> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`/api/conversations/${conversationId}/attachments`, {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json" },
    body,
  });
  if (!response.ok) {
    throw new Error("附件上传失败");
  }
  return (await response.json()) as Attachment;
}

export async function deleteAttachment({
  conversationId,
  attachmentId,
}: {
  conversationId: string;
  attachmentId: string;
}): Promise<void> {
  const response = await fetch(
    `/api/conversations/${conversationId}/attachments/${attachmentId}`,
    { method: "DELETE", credentials: "include", headers: { Accept: "application/json" } },
  );
  if (!response.ok) {
    throw new Error("附件删除失败");
  }
}

export function attachmentDownloadUrl(conversationId: string, attachmentId: string): string {
  return `/api/conversations/${conversationId}/attachments/${attachmentId}/download`;
}
