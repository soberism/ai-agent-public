import { useCallback, useState } from "react";

export function useToast() {
  const [notice, setNotice] = useState("");
  const [tone, setTone] = useState<"success" | "error">("success");
  const [revision, setRevision] = useState(0);
  const notify = useCallback((message: string, nextTone: "success" | "error" = "success") => {
    setNotice(message);
    setTone(nextTone);
    setRevision((value) => value + 1);
  }, []);
  const close = useCallback(() => setNotice(""), []);
  return {
    notice,
    setNotice: notify,
    toastProps: { key: revision, message: notice, tone, onClose: close },
  };
}
