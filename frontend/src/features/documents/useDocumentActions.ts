import type { RefObject } from "react";
import { useSession } from "../../app/session";
import { useSharingEditor } from "../sharing/useSharingEditor";
import type { SourceMaterial } from "./types";

export function useDocumentActions({
  load,
  fileRef,
  folderId,
  closeUpload,
  selectFolder,
}: {
  load: () => Promise<void>;
  fileRef: RefObject<HTMLInputElement | null>;
  folderId: string;
  closeUpload: () => void;
  selectFolder: (id: string) => void;
}) {
  const { call } = useSession();
  const materialSharing = useSharingEditor("material");
  async function upload() {
    const file = fileRef.current?.files?.[0];
    if (!file) throw new Error("请选择文件");
    if (file.size > 20 * 1024 * 1024) throw new Error("单个文件不能超过 20 MiB");
    const form = new FormData();
    form.append("file", file);
    form.append("recognize", "false");
    if (folderId) form.append("folder_id", folderId);
    await materialSharing.save(() =>
      call<SourceMaterial>("/documents/materials", { method: "POST", body: form }),
    );
    materialSharing.reset();
    closeUpload();
    await load();
  }
  async function addFolder(form: HTMLFormElement) {
    const name = String(new FormData(form).get("name") ?? "");
    await call<{ id: string }>("/documents/folders", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    form.reset();
    await load();
  }
  async function move(item: SourceMaterial, nextFolder: string) {
    await call(`/documents/materials/${item.id}`, {
      method: "PATCH",
      body: JSON.stringify({ folder_id: nextFolder || null }),
    });
    await load();
  }
  async function remove(item: SourceMaterial) {
    await call(`/documents/materials/${item.id}`, { method: "DELETE", body: "{}" });
    await load();
  }
  async function rename(item: SourceMaterial, name: string) {
    await call(`/documents/materials/${item.id}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    });
    await load();
  }
  return { upload, addFolder, move, remove, rename, materialSharing, selectFolder };
}
