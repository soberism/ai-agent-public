import Input from "@rc-component/input";
import { useDocumentActions } from "./useDocumentActions";
import { SharingEditor } from "../sharing/SharingEditor";
import { useLocation } from "react-router-dom";
import { DocumentUpload } from "./DocumentUpload";
import { DocumentFolders } from "./DocumentFolders";
import { useToast } from "../../shared/useToast";
import { Toast } from "../../shared/Toast";
import { Select } from "../../shared/Select";
import { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { Loading } from "../../shared/Loading";
import { PageHeader } from "../../shared/PageHeader";
import { DocumentMaterialList } from "./DocumentMaterialList";
import type { DocumentFolder, SourceMaterial } from "./types";

export function DocumentsPage() {
  const { call } = useSession();
  const location = useLocation();
  const [materials, setMaterials] = useState<SourceMaterial[]>([]);
  const [folders, setFolders] = useState<DocumentFolder[]>([]);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [directory, setDirectory] = useState(
    new URLSearchParams(location.search).get("folder") ?? "all",
  );
  const [query, setQuery] = useState("");
  const [folderId, setFolderId] = useState("");
  const { setNotice: setError, toastProps } = useToast();
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const load = useCallback(async () => {
    try {
      const data = await call<{ items: SourceMaterial[]; folders: DocumentFolder[] }>(
        "/documents/materials",
      );
      setMaterials(data.items);
      setFolders(data.folders);
      setError("");
    } catch (failure) {
      setError(messageOf(failure), "error");
    } finally {
      setLoaded(true);
    }
  }, [call, setError]);
  useEffect(() => void load(), [load]);
  useEffect(() => {
    if (!loaded || !location.hash) return;
    const target = document.getElementById(location.hash.slice(1));
    if (!target) return;
    if (target instanceof HTMLDetailsElement) {
      const panel = target.closest(".document-folders");
      if (panel instanceof HTMLDetailsElement) panel.open = true;
      target.open = true;
    }
    target.scrollIntoView({ block: "center" });
  }, [loaded, materials, folders, location.hash]);

  function openUpload() {
    setFolderId(directory === "all" ? "" : directory);
    setUploadOpen(true);
  }

  const actions = useDocumentActions({
    load,
    fileRef,
    folderId,
    closeUpload: () => setUploadOpen(false),
    selectFolder: setDirectory,
  });
  async function upload(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await actions.upload();
    } catch (failure) {
      setError(messageOf(failure), "error");
    } finally {
      setBusy(false);
    }
  }
  async function addFolder(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await actions.addFolder(event.currentTarget);
    } catch (failure) {
      setError(messageOf(failure), "error");
    }
  }
  const visible = materials.filter(
    (item) =>
      (directory === "all" || (item.folder_id ?? "") === directory) &&
      item.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()),
  );

  return (
    <main className="page feature-page documents-page">
      <PageHeader title="材料管理" />
      <div className="section-heading">
        <p className="muted">按目录保存和整理你的文件</p>
        <button className="primary" onClick={openUpload}>
          上传文件
        </button>
      </div>
      <label className="sr-only" htmlFor="material-search">
        搜索文件
      </label>
      <Input
        id="material-search"
        type="search"
        placeholder="搜索文件名称"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <label>
        所在目录
        <Select value={directory} onChange={(e) => setDirectory(e.target.value)}>
          <option value="all">全部文件（{materials.length}）</option>
          <option value="">未分类（{materials.filter((item) => !item.folder_id).length}）</option>
          {folders.map((folder) => (
            <option key={folder.id} value={folder.id}>
              {folder.name}（{folder.count}）
            </option>
          ))}
        </Select>
      </label>
      <Toast {...toastProps} />
      {uploadOpen && (
        <DocumentUpload
          folders={folders}
          uncategorizedCount={materials.filter((item) => !item.folder_id).length}
          folderId={folderId}
          setFolderId={setFolderId}
          busy={busy}
          fileRef={fileRef}
          upload={upload}
          locked={actions.materialSharing.recovering}
          visibility={<SharingEditor sharing={actions.materialSharing} disabled={busy} />}
          close={() => {
            if (!busy) setUploadOpen(false);
          }}
        />
      )}
      <section className="document-library">
        <div className="section-heading">
          <h2>
            文件 <small>{visible.length} 份</small>
          </h2>
        </div>
        {!loaded ? (
          <Loading compact />
        ) : (
          <DocumentMaterialList
            items={visible}
            uncategorizedCount={materials.filter((item) => !item.folder_id).length}
            folders={folders}
            move={actions.move}
            remove={actions.remove}
            rename={actions.rename}
          />
        )}
      </section>
      <DocumentFolders
        folders={folders}
        materials={materials}
        reload={load}
        addFolder={addFolder}
        selectFolder={setDirectory}
      />
    </main>
  );
}
