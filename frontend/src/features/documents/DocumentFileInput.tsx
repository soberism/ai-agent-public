import { useState } from "react";
import type { RefObject } from "react";

export function DocumentFileInput({
  inputRef,
  disabled = false,
}: {
  inputRef: RefObject<HTMLInputElement | null>;
  disabled?: boolean;
}) {
  const [name, setName] = useState("");
  return (
    <div className="document-file-picker">
      <span className="document-file-choose" aria-hidden="true">
        选择文件
      </span>
      <span className="document-file-name" aria-hidden="true" title={name}>
        {name || "未选择任何文件"}
      </span>
      <input
        disabled={disabled}
        ref={inputRef}
        type="file"
        required
        onChange={(event) => setName(event.target.files?.[0]?.name ?? "")}
      />
    </div>
  );
}
