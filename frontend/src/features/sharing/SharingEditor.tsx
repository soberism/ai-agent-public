import { SharingFields } from "./SharingFields";
import type { useSharingEditor } from "./useSharingEditor";

export function SharingEditor({
  sharing,
  disabled = false,
}: {
  sharing: ReturnType<typeof useSharingEditor>;
  disabled?: boolean;
}) {
  if (sharing.ready && !sharing.canEdit) return null;
  return (
    <div className="stack wide-field sharing-editor">
      {!sharing.ready ? (
        <p role="status">正在加载可见范围…</p>
      ) : (
        <SharingFields
          policy={sharing.policy}
          homes={sharing.homes}
          change={sharing.setPolicy}
          disabled={disabled}
        />
      )}
      {sharing.error && (
        <p role="alert" className="error">
          {sharing.error}
          <button type="button" className="text-button" onClick={() => void sharing.retry()}>
            重试
          </button>
        </p>
      )}
      {sharing.recovering && (
        <p role="alert" className="error">
          内容已保存，当前仅重试可见范围；完成后再编辑内容。
        </p>
      )}
    </div>
  );
}
