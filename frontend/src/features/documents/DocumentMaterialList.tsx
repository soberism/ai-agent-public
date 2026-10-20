import Input from "@rc-component/input";
import { useSharingEditor } from "../sharing/useSharingEditor";
import { SharingEditor } from "../sharing/SharingEditor";
import { VisibilityControl } from "../sharing/VisibilityControl";
import { useState } from "react";
import { ConfirmButton } from "../../shared/ConfirmButton";
import { Modal } from "../../shared/Modal";
import { Select } from "../../shared/Select";
import { useToast } from "../../shared/useToast";
import { Toast } from "../../shared/Toast";
import { messageOf } from "../../shared/api";
import type { DocumentFolder, SourceMaterial } from "./types";

export function DocumentMaterialList({
  items,
  folders,
  uncategorizedCount,
  move,
  remove,
  rename,
}: {
  items: SourceMaterial[];
  folders: DocumentFolder[];
  uncategorizedCount: number;
  move: (item: SourceMaterial, folderId: string) => Promise<void>;
  remove: (item: SourceMaterial) => Promise<void>;
  rename: (item: SourceMaterial, name: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState<SourceMaterial | null>(null);
  const [name, setName] = useState("");
  const sharing = useSharingEditor("material", editing?.id);
  const { setNotice: setError, toastProps } = useToast();
  const [busy, setBusy] = useState(false);
  const [confirmExtension, setConfirmExtension] = useState(false);
  function extension(value: string) {
    const trimmed = value.trim();
    const dot = trimmed.lastIndexOf(".");
    return dot > 0 ? trimmed.slice(dot + 1).toLowerCase() : "";
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!editing || busy) return;
    if (extension(editing.name) !== extension(name)) {
      setConfirmExtension(true);
      return;
    }
    await persist();
  }
  async function persist() {
    if (!editing || busy) return;
    setBusy(true);
    try {
      await sharing.save(async () => {
        await rename(editing, name);
        return { id: editing.id };
      });
      setEditing(null);
    } catch (failure) {
      setError(messageOf(failure), "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Toast {...toastProps} />
      {!items.length ? (
        <div className="document-empty">
          <strong>暂无文件</strong>
          <p>上传文件，或切换目录和搜索条件。</p>
        </div>
      ) : (
        <ul className="plain-list document-materials">
          {items.map((item) => (
            <li key={item.id} id={`material-${item.id}`}>
              <div className="material-file-heading">
                <span className="material-file-type" aria-hidden="true">
                  {item.name.includes(".")
                    ? item.name.split(".").pop()?.slice(0, 5).toUpperCase()
                    : "FILE"}
                </span>
                <div className="material-file-info">
                  <strong>{item.name}</strong>
                  <div className="material-file-meta">
                    {" "}
                    <span>{new Date(item.created_at).toLocaleString("zh-CN")}</span>{" "}
                    <div className="material-directory">
                      <Select
                        aria-label={`移动 ${item.name}`}
                        value={item.folder_id ?? ""}
                        onChange={(event) => void move(item, event.target.value)}
                      >
                        <option value="">未分类（{uncategorizedCount} 份）</option>
                        {folders.map((folder) => (
                          <option value={folder.id} key={folder.id}>
                            {folder.name}（{folder.count} 份）
                          </option>
                        ))}
                      </Select>
                    </div>
                  </div>
                </div>
              </div>
              <div className="material-actions">
                <VisibilityControl kind="material" id={item.id} />
                <a
                  href={`/api/documents/materials/${item.id}/content`}
                  target="_blank"
                  rel="noreferrer"
                >
                  查看文件
                </a>
                <a href={`/api/documents/materials/${item.id}/download`}>下载</a>

                <button
                  className="text-button"
                  onClick={() => {
                    setConfirmExtension(false);
                    setEditing(item);
                    setName(item.name);
                    setError("");
                  }}
                >
                  重命名
                </button>
                <ConfirmButton
                  className="text-button error"
                  title="删除文件"
                  message={`确认删除“${item.name}”吗？删除后无法恢复。`}
                  onConfirm={() => remove(item)}
                >
                  删除
                </ConfirmButton>
              </div>
            </li>
          ))}
        </ul>
      )}
      {editing && (
        <Modal
          title="重命名文件"
          close={() => {
            if (!busy) setEditing(null);
          }}
        >
          {confirmExtension ? (
            <div className="stack">
              <p>
                更改文件后缀可能导致文件无法正常打开。确认将“{editing.name}”改为“{name.trim()}”吗？
              </p>
              <div className="modal-actions">
                <button disabled={busy} onClick={() => setConfirmExtension(false)}>
                  返回修改
                </button>
                <button className="primary" disabled={busy} onClick={() => void persist()}>
                  {busy ? "保存中…" : "确认更改"}
                </button>
              </div>
            </div>
          ) : (
            <form className="stack" onSubmit={save}>
              <label>
                文件名称
                <Input
                  disabled={busy || sharing.recovering}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  maxLength={255}
                  autoFocus
                />
              </label>
              <SharingEditor sharing={sharing} disabled={busy} />
              <button className="primary" disabled={busy || !name.trim()}>
                {busy ? "保存中…" : "保存"}
              </button>
            </form>
          )}
        </Modal>
      )}
    </>
  );
}
