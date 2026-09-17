import { ChangeEvent, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  attachmentDownloadUrl,
  deleteAttachment,
  listAttachments,
  uploadAttachment,
} from "../api/attachments";

interface AttachmentPanelProps {
  conversationId: string;
  isArchived: boolean;
}

const parseStatusLabels = {
  pending: "等待解析",
  parsing: "解析中",
  success: "解析完成",
  failed: "解析失败",
};

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function AttachmentPanel({ conversationId, isArchived }: AttachmentPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  const attachments = useQuery({
    queryKey: ["attachments", conversationId],
    queryFn: () => listAttachments(conversationId),
  });
  const upload = useMutation({
    mutationFn: uploadAttachment,
    onSuccess: async () => {
      if (inputRef.current) inputRef.current.value = "";
      await queryClient.invalidateQueries({ queryKey: ["attachments", conversationId] });
    },
  });
  const remove = useMutation({
    mutationFn: deleteAttachment,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["attachments", conversationId] });
    },
  });

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) upload.mutate({ conversationId, file });
  }

  function handleDelete(attachmentId: string, fileName: string) {
    if (window.confirm(`确定删除附件“${fileName}”吗？`)) {
      remove.mutate({ conversationId, attachmentId });
    }
  }

  return (
    <section className="attachment-panel" aria-labelledby="attachment-title">
      <div className="attachment-heading">
        <div>
          <span className="eyebrow">会话资料</span>
          <h4 id="attachment-title">附件</h4>
        </div>
        <label className={isArchived || upload.isPending ? "upload-button disabled" : "upload-button"}>
          {upload.isPending ? "上传中…" : "上传附件"}
          <input
            ref={inputRef}
            type="file"
            accept=".csv,.xlsx,.json,.txt"
            disabled={isArchived || upload.isPending}
            onChange={handleFileChange}
          />
        </label>
      </div>
      <p className="attachment-hint">支持 CSV、XLSX、JSON、TXT，单个文件不超过 20 MB。</p>
      {attachments.isPending && <p className="muted">正在读取附件……</p>}
      {attachments.isError && <p className="error">附件列表读取失败，请稍后重试。</p>}
      {upload.isError && <p className="error">上传失败，请检查格式和文件大小。</p>}
      {remove.isError && <p className="error">附件删除失败，请稍后重试。</p>}
      {attachments.data?.length === 0 && <p className="muted">还没有附件。</p>}
      {attachments.data && attachments.data.length > 0 && (
        <ul className="attachment-list">
          {attachments.data.map((attachment) => (
            <li key={attachment.id}>
              <div>
                <strong>{attachment.file_name}</strong>
                <span>
                  {formatFileSize(attachment.file_size)} · {parseStatusLabels[attachment.parse_status]}
                </span>
              </div>
              <div className="attachment-actions">
                <a href={attachmentDownloadUrl(conversationId, attachment.id)}>下载</a>
                <button
                  type="button"
                  disabled={remove.isPending}
                  onClick={() => handleDelete(attachment.id, attachment.file_name)}
                >
                  删除
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
