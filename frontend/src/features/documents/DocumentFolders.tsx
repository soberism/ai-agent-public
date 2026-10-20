import Input from "@rc-component/input";
import { useSession } from "../../app/session";
import { ConfirmButton } from "../../shared/ConfirmButton";
import type { SourceMaterial, DocumentFolder } from "./types";

export function DocumentFolders({
  folders,
  materials,
  reload,
  addFolder,
  selectFolder,
}: {
  folders: DocumentFolder[];
  materials: SourceMaterial[];
  reload: () => Promise<void>;
  selectFolder: (id: string) => void;
  addFolder: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
}) {
  const { call } = useSession();
  async function removeFolder(id: string) {
    await call(`/documents/folders/${id}`, { method: "DELETE" });
    selectFolder("all");
    await reload();
  }
  return (
    <details className="feature-card document-folders">
      <summary>
        <span className="directory-summary-title">管理目录</span>
        <span className="directory-summary-meta">
          {folders.length} 个{" "}
          <svg
            className="directory-chevron"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            aria-hidden="true"
          >
            <path d="m4 6 4 4 4-4" />
          </svg>
        </span>
      </summary>
      <form className="inline-create" onSubmit={addFolder}>
        <label className="sr-only" htmlFor="folder-name">
          目录名称
        </label>
        <Input
          autoComplete="off"
          id="folder-name"
          name="name"
          required
          maxLength={40}
          placeholder="新目录名称"
        />
        <button>新建</button>
      </form>
      <ul className="plain-list">
        {folders.map((folder) => (
          <li key={folder.id}>
            <details className="directory-detail" id={`directory-${folder.id}`}>
              <summary className="directory-item" onClick={() => selectFolder(folder.id)}>
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  aria-hidden="true"
                >
                  <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
                </svg>
                <strong>{folder.name}</strong>
                <span>{folder.count} 份文件</span>
                <span className="directory-item-chevron" aria-hidden="true">
                  ›
                </span>
              </summary>
              <div className="directory-content">
                {materials.filter((item) => item.folder_id === folder.id).length ? (
                  <ul className="directory-files">
                    {materials
                      .filter((item) => item.folder_id === folder.id)
                      .map((item) => (
                        <li key={item.id}>
                          <div className="directory-file-row">
                            <span className="directory-file-type" aria-hidden="true">
                              {item.name.includes(".")
                                ? item.name.split(".").pop()?.slice(0, 5).toUpperCase()
                                : "FILE"}
                            </span>
                            <span className="directory-file-name" title={item.name}>
                              {item.name}
                            </span>
                            <div className="directory-file-actions">
                              <a
                                href={`/api/documents/materials/${item.id}/download`}
                                aria-label={`下载 ${item.name}`}
                              >
                                下载
                              </a>
                            </div>
                          </div>
                        </li>
                      ))}
                  </ul>
                ) : (
                  <p className="muted">此目录暂无文件</p>
                )}
                <div className="directory-footer">
                  {folder.editable !== false && (
                    <ConfirmButton
                      className="text-button error"
                      title="删除目录"
                      message={`确认删除“${folder.name}”目录吗？目录内的文件会移到“未分类”，不会删除文件。`}
                      onConfirm={() => removeFolder(folder.id)}
                    >
                      删除目录
                    </ConfirmButton>
                  )}
                </div>
              </div>
            </details>
          </li>
        ))}
      </ul>
      {!folders.length && <p className="muted directory-empty">还没有目录，新建一个开始整理。</p>}
    </details>
  );
}
