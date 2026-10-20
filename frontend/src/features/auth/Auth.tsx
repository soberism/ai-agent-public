import { Link, Navigate } from "react-router-dom";
import { useAuthForm } from "./useAuthForm";
import { AuthFields } from "./AuthFields";
import { Loading } from "../../shared/Loading";
import { Toast } from "../../shared/Toast";
export function Auth({ register = false }: { register?: boolean }) {
  const form = useAuthForm({ register });
  const { session, navigate, destination, pending, error, wait, loginRequired, submit } = form;
  if (session.state === "unknown") return <Loading />;
  if (session.user) return <Navigate to={destination} replace />;
  if (session.state === "error")
    return (
      <div className="state">
        <Toast message={session.notice} tone="error" />
        <button onClick={() => void session.verify()}>重新连接</button>
      </div>
    );
  return (
    <main className="auth page">
      <div className="brand">
        <span aria-hidden="true">☀</span> 安排儿
      </div>
      <header>
        <p className="eyebrow">把日常安排，放在一起</p>
        <h1>{register ? "创建你的账号" : "登录安排儿"}</h1>
        <p className="muted">
          {register ? "从第一条待办开始，让生活更从容。" : "登录后，继续安排自己的每一天。"}
        </p>
      </header>
      {session.authBusy && !pending && <Loading compact />}
      <Toast message={session.notice} tone="error" />
      <form onSubmit={submit} noValidate className="stack">
        <AuthFields form={form} register={register} />
        <Toast
          key={form.feedbackRevision}
          message={error || Object.values(form.fields).find(Boolean) || ""}
          tone="error"
        />
        <button
          className="primary"
          disabled={
            pending || form.verification.sending || session.authBusy || wait > 0 || loginRequired
          }
        >
          {wait ? `请 ${wait} 秒后重试` : register ? "创建账号" : "登录"}
        </button>
      </form>
      <p className="auth-switch">
        {register ? "已有账号？" : "还没有账号？"}
        <Link
          aria-disabled={pending}
          onClick={(event) => {
            if (pending) {
              event.preventDefault();
              return;
            }
            if (
              event.button === 0 &&
              !event.metaKey &&
              !event.ctrlKey &&
              !event.shiftKey &&
              !event.altKey
            ) {
              event.preventDefault();
              navigate(
                `${register ? "/login" : "/register"}?returnTo=${encodeURIComponent(destination)}`,
                { flushSync: true },
              );
            }
          }}
          to={`${register ? "/login" : "/register"}?returnTo=${encodeURIComponent(destination)}`}
        >
          {register ? "去登录" : "去注册"}
        </Link>
      </p>
      <p className="small muted">仅限受控内测 · 邮箱用于账号登录</p>
    </main>
  );
}
