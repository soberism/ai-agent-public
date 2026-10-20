import Input from "@rc-component/input";
import { useState } from "react";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { Toast } from "../../shared/Toast";
import { Modal } from "../../shared/Modal";

export function ChangePassword() {
  const session = useSession();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const close = () => {
    if (busy) return;
    setOpen(false);
    setCurrent("");
    setNext("");
    setConfirm("");
    setError("");
  };

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (next !== confirm) {
      setError("两次密码输入不一致");
      return;
    }
    if (next === current) {
      setError("新密码不能与原密码相同");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await session.call("/auth/password", {
        method: "POST",
        body: JSON.stringify({
          current_password: current,
          new_password: next,
          confirm_password: confirm,
        }),
      });
      setOpen(false);
      setCurrent("");
      setNext("");
      setConfirm("");
      await session.logout();
    } catch (cause) {
      setError(messageOf(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button type="button" className="account-deactivate" onClick={() => setOpen(true)}>
        修改密码
      </button>
      {open && (
        <Modal title="修改密码" close={close}>
          <form className="stack" onSubmit={submit}>
            <div>
              <label htmlFor="current-password">原密码</label>
              <Input
                id="current-password"
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={(event) => setCurrent(event.target.value)}
                minLength={12}
                maxLength={128}
                disabled={busy}
                required
              />
            </div>
            <div>
              <label htmlFor="new-password">新密码</label>
              <Input
                id="new-password"
                type="password"
                autoComplete="new-password"
                value={next}
                onChange={(event) => setNext(event.target.value)}
                minLength={12}
                maxLength={128}
                disabled={busy}
                required
              />
              <p className="muted small">12–128 个字符，可以包含空格与中文</p>
            </div>
            <div>
              <label htmlFor="confirm-new-password">确认新密码</label>
              <Input
                id="confirm-new-password"
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                minLength={12}
                maxLength={128}
                disabled={busy}
                required
              />
            </div>
            {error && <Toast message={error} tone="error" />}
            <div className="modal-actions">
              <button type="button" disabled={busy} onClick={close}>
                取消
              </button>
              <button className="primary" disabled={busy}>
                {busy ? "修改中…" : "确认修改"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
