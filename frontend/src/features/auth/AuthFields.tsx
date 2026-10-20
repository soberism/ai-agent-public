import Input from "@rc-component/input";
import { useState } from "react";
import type { useAuthForm } from "./useAuthForm";
import { VerificationField } from "./VerificationField";
export function AuthFields({
  form,
  register,
}: {
  form: ReturnType<typeof useAuthForm>;
  register: boolean;
}) {
  const {
    email,
    setEmail,
    password,
    setPassword,
    confirm,
    setConfirm,
    pending,
    fields,
    verification,
    session,
  } = form;
  const [visible, setVisible] = useState(false);
  return (
    <>
      <div>
        <label htmlFor="email">邮箱</label>
        <Input
          id="email"
          type="email"
          autoComplete="username"
          inputMode="email"
          value={email}
          disabled={pending}
          onChange={(event) => setEmail(event.target.value)}
          aria-invalid={!!fields.email}

          placeholder="你的邮箱地址"
        />
      </div>
      {register && (
        <VerificationField
          verification={verification}
          disabled={pending || session.authBusy}
          error={fields.verification_code}
        />
      )}
      <div>
        <label htmlFor="password">密码</label>
        <div className="password">
          <Input
            id="password"
            type={visible ? "text" : "password"}
            autoComplete={register ? "new-password" : "current-password"}
            value={password}
            disabled={pending}
            onChange={(event) => setPassword(event.target.value)}
            aria-invalid={!!fields.password}
            aria-describedby="password-help"
          />
          <button
            type="button"
            className="text-button"
            aria-label={visible ? "隐藏密码" : "显示密码"}
            aria-pressed={visible}
            onClick={() => setVisible(!visible)}
          >
            {visible ? "隐藏" : "显示"}
          </button>
        </div>
        <span id="password-help" className="muted">
          12–128 个字符，可以包含空格与中文
        </span>
      </div>
      {register && (
        <div>
          <label htmlFor="confirm">确认密码</label>
          <Input
            id="confirm"
            type={visible ? "text" : "password"}
            autoComplete="new-password"
            value={confirm}
            disabled={pending}
            onChange={(event) => setConfirm(event.target.value)}
            aria-invalid={!!fields.confirm_password}
          />
        </div>
      )}
    </>
  );
}
