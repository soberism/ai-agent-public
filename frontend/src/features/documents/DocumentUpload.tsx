import type { ReactNode } from "react";
import type { RefObject } from "react";
import { Modal } from "../../shared/Modal";
import { Select } from "../../shared/Select";
import { DocumentFileInput } from "./DocumentFileInput";
import type { DocumentFolder } from "./types";

export function DocumentUpload({
  folders,
  uncategorizedCount,
  visibility,
  locked = false,
  folderId,
  setFolderId,
  busy,
  fileRef,
  upload,
  close,
}: {
  folders: DocumentFolder[];
  uncategorizedCount: number;
  visibility?: ReactNode;
  locked?: boolean;
  folderId: string;
  setFolderId: (value: string) => void;
  busy: boolean;
  fileRef: RefObject<HTMLInputElement | null>;
  upload: (event: React.FormEvent) => Promise<void>;
  close: () => void;
}) {
  return (
    <Modal className="document-upload-dialog" title="上传文件" close={close}>
      <form className="stack document-upload" onSubmit={upload}>
        <label>
          选择文件
          <DocumentFileInput inputRef={fileRef} disabled={locked} />
        </label>
        <label>
          保存到目录
          <Select disabled={locked} value={folderId} onChange={(e) => setFolderId(e.target.value)}>
            <option value="">未分类（{uncategorizedCount} 份）</option>
            {folders.map((folder) => (
              <option key={folder.id} value={folder.id}>
                {folder.name}（{folder.count} 份）
              </option>
            ))}
          </Select>
        </label>
        {visibility}
        <button className="primary" disabled={busy}>
          {busy ? "上传中…" : "上传保存"}
        </button>
        <p className="muted document-upload-note">仅保存原文件，单个文件不超过 20 MiB。</p>
      </form>
    </Modal>
  );
}
