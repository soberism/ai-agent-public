import { useEffect, useRef, useState } from "react";
import { ApiError, messageOf, request } from "../../shared/api";
import { codepoints } from "../../shared/text";

export function useEmailVerification(email: string) {
  const [code, setCode] = useState("");
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now);
  const deadlines = useRef(new Map<string, number>());
  const operation = useRef(0);
  const alive = useRef(false);
  const normalized = email.trim().toLowerCase();
  const wait = Math.max(0, Math.ceil(((deadlines.current.get(normalized) ?? 0) - now) / 1000));
  useEffect(() => {
    alive.current = true;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      alive.current = false;
      clearInterval(timer);
    };
  }, []);
  function reset() {
    operation.current++;
    setCode("");
    setNotice("");
    setError("");
    setSending(false);
    setNow(Date.now());
  }
  async function send() {
    if (sending || wait) return;
    setNotice("");
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized) || codepoints(normalized) > 254) {
      setError("请输入有效的邮箱地址");
      return;
    }
    setError("");
    setSending(true);
    const attempt = ++operation.current;
    const current = () => alive.current && attempt === operation.current;
    try {
      const result = await request<{ expires_in: number; retry_after: number }>(
        "/auth/register/code",
        { method: "POST", body: JSON.stringify({ email: normalized }) },
      );
      if (!alive.current) return;
      deadlines.current.set(normalized, Date.now() + result.retry_after * 1000);
      if (!current()) return;
      setNow(Date.now());
      setCode("");
      setNotice(
        `验证码邮件已发送，请检查收件箱或垃圾邮件，${Math.ceil(result.expires_in / 60)}分钟内有效`,
      );
    } catch (failure) {
      if (!alive.current) return;
      if (failure instanceof ApiError && failure.retryAfter > 0)
        deadlines.current.set(normalized, Date.now() + failure.retryAfter * 1000);
      if (!current()) return;
      setNow(Date.now());
      setError(messageOf(failure));
    } finally {
      if (current()) setSending(false);
    }
  }
  return { code, setCode, sending, notice, error, wait, reset, send, clearCode: () => setCode("") };
}
