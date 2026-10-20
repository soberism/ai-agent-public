import { useCallback, useContext } from "react";
import { Context } from "./context";
import { Toast } from "../../shared/Toast";
export function Notice() {
  const { notice, noticeTone, notify } = useContext(Context);
  const close = useCallback(() => notify(""), [notify]);
  return <Toast message={notice} tone={noticeTone} onClose={close} />;
}
