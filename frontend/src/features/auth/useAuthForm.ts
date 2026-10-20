import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, messageOf, request } from "../../shared/api";
import type { User } from "./types";
import { codepoints } from "../../shared/text";
import { safeReturnTo } from "./rules";
import { useEmailVerification } from "./useEmailVerification";
import { useSession } from "../../app/session";
export function useAuthForm({ register = false }: { register?: boolean }) {
  const session = useSession();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [email, updateEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const verification = useEmailVerification(email);
  function setEmail(value: string) {
    if (value.trim().toLowerCase() !== email.trim().toLowerCase()) {
      verification.reset();
      setFields({});
    }
    updateEmail(value);
  }
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [feedbackRevision, setFeedbackRevision] = useState(0);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [wait, setWait] = useState(0);
  const [loginRequired, setLoginRequired] = useState(false);
  useEffect(() => {
    if (!wait) return;
    const timer = setTimeout(() => setWait(wait - 1), 1000);
    return () => clearTimeout(timer);
  }, [wait]);
  const alive = useRef(false);
  const operation = useRef(0);
  useEffect(() => {
    const operations = operation;
    alive.current = true;
    return () => {
      alive.current = false;
      operations.current++;
    };
  }, []);
  const destination = safeReturnTo(params.get("returnTo"));
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (pending || verification.sending || session.authBusy || wait || loginRequired) return;
    setFeedbackRevision((value) => value + 1);
    const normalized = email.trim().toLowerCase();
    const errors: Record<string, string> = {};
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized) || codepoints(normalized) > 254)
      errors.email = "请输入有效的邮箱地址";
    if (codepoints(password) < 12 || codepoints(password) > 128)
      errors.password = "密码需要 12–128 个字符";
    if (register && confirm !== password) errors.confirm_password = "两次输入的密码不一致";
    if (register && !/^\d{6}$/.test(verification.code))
      errors.verification_code = "请输入六位数字验证码";
    setFields(errors);
    setError("");
    if (Object.keys(errors).length) return;
    setPending(true);
    session.beginAuth();
    const attempt = ++operation.current;
    const generation = session.generation.current;
    const current = () =>
      alive.current && attempt === operation.current && generation === session.generation.current;
    try {
      const user = await request<User>(register ? "/auth/register" : "/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: normalized,
          password,
          ...(register ? { confirm_password: confirm, verification_code: verification.code } : {}),
        }),
      });
      if (!current()) return;
      session.establish(user);
      setPassword("");
      setConfirm("");
      navigate(register ? "/" : destination, { replace: true });
    } catch (failure) {
      if (!current()) return;
      if (failure instanceof ApiError) {
        setFields(failure.fields);
        setWait(failure.retryAfter);
        if (failure.code === "REGISTRATION_FAILED") {
          verification.clearCode();
          setError("注册未完成，请重新获取验证码；也可以先尝试登录核对账号状态");
          return;
        }
        if (
          failure.code === "ACCOUNT_CREATED_LOGIN_REQUIRED" ||
          (register && (failure.status === 0 || failure.status >= 500))
        ) {
          setLoginRequired(true);
          setError(
            failure.code === "ACCOUNT_CREATED_LOGIN_REQUIRED"
              ? "账号已创建，请重新登录"
              : "注册结果尚未确认，请先尝试登录，不要重复注册",
          );
          return;
        }
        if (!register && failure.status === 0) {
          try {
            const user = await request<User>("/auth/me");
            if (!current()) return;
            session.establish(user);
            navigate(destination, { replace: true });
            return;
          } catch {
            if (!current()) return;
            setError("登录结果尚未确认，请恢复网络后重新登录");
            return;
          }
        }
      }
      setError(messageOf(failure));
    } finally {
      const abandoned = !alive.current || attempt !== operation.current;
      if (!abandoned) setPending(false);
      session.endAuth(abandoned);
    }
  }
  return {
    session,
    navigate,
    destination,
    email,
    setEmail,
    password,
    setPassword,
    confirm,
    setConfirm,
    pending,
    error,
    feedbackRevision,
    fields,
    wait,
    loginRequired,
    verification,
    submit,
  };
}
