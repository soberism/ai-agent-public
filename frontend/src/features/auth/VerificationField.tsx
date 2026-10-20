import Input from "@rc-component/input";
import { Toast } from "../../shared/Toast";
import type { useEmailVerification } from "./useEmailVerification";

export function VerificationField({
  verification,
  disabled,
  error,
}: {
  verification: ReturnType<typeof useEmailVerification>;
  disabled: boolean;
  error?: string;
}) {
  return (
    <div>
      <label htmlFor="verification-code">邮箱验证码</label>
      <div className="verification-row">
        <Input
          id="verification-code"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          value={verification.code}
          disabled={disabled}
          onChange={(event) => verification.setCode(event.target.value.replace(/\D/g, ""))}
          aria-invalid={!!error}
          aria-describedby="verification-help"
          placeholder="六位数字验证码"
        />
        <button
          type="button"
          disabled={disabled || verification.sending || verification.wait > 0}
          onClick={() => void verification.send()}
        >
          {verification.wait ? `${verification.wait} 秒后重发` : "发送验证码"}
        </button>
      </div>
      <div id="verification-help">
        {verification.error && <Toast message={verification.error} tone="error" />}
        {verification.notice && <Toast message={verification.notice} />}
      </div>
    </div>
  );
}
