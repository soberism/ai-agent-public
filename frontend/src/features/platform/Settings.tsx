import Input from "@rc-component/input";
import { ConfirmButton } from "../../shared/ConfirmButton";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { usePlatform } from "./AppShell";
import { Toast } from "../../shared/Toast";
import { useToast } from "../../shared/useToast";
import { ChangePassword } from "./ChangePassword";

export function Settings() {
  const session = useSession();
  const { settings, settingsError, updateSettings } = usePlatform();
  const [nickname, setNickname] = useState(session.user!.nickname ?? "");
  const [busy, setBusy] = useState(false);
  const { setNotice, toastProps } = useToast();
  useEffect(() => {
    setNickname(settings?.nickname ?? session.user!.nickname ?? "");
  }, [settings, session.user]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setNotice("");
    try {
      await updateSettings({ nickname: nickname.trim(), timezone: "Asia/Shanghai" });
      setNotice("设置已更新");
    } catch (error) {
      setNotice(messageOf(error), "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page platform-page">
      <header className="platform-header">
        <h1>我的</h1>
      </header>
      {settingsError && <Toast message={["设置加载失败：", settingsError].join("")} tone="error" />}
      <section className="settings-card">
        <h2>账号</h2>
        <p className="account-email">{session.user!.email}</p>
      </section>
      <form className="settings-card stack" onSubmit={save}>
        <div>
          <label htmlFor="nickname">昵称</label>
          <Input
            autoComplete="off"
            id="nickname"
            value={nickname}
            onChange={(event) => setNickname(event.target.value)}
            minLength={1}
            maxLength={30}
            required
          />
          <p className="muted small">用于头像和家庭成员列表，最多30个字符。</p>
        </div>
        <div>
          <span>时区</span>
          <p>上海（UTC+8）</p>
        </div>
        <Toast {...toastProps} />
        <button
          className="primary"
          disabled={
            busy ||
            !nickname.trim() ||
            (nickname.trim() === settings?.nickname && settings?.timezone === "Asia/Shanghai")
          }
        >
          {busy ? "保存中…" : "保存设置"}
        </button>
      </form>
      <section className="settings-card">
        <h2>订阅</h2>
        <p className="muted" id="subscription-unavailable">
          订阅服务暂未开放。
        </p>
        <button disabled aria-describedby="subscription-unavailable">
          管理订阅
        </button>
      </section>
      <section className="settings-card">
        <h2>邮件摘要</h2>
        <p className="muted">按设定时间发送每日、每周待办摘要，也可手动发送。</p>
        <Link className="button" to="/connections">
          管理摘要
        </Link>
      </section>
      <section className="settings-card">
        <h2>通知</h2>
        <p className="muted" id="notifications-unavailable">
          站内通知暂未开放。
        </p>
        <button disabled aria-describedby="notifications-unavailable">
          查看站内通知
        </button>
      </section>
      <section className="settings-card">
        <h2>AI 偏好</h2>
        <p className="muted">管理助手称呼、表达偏好与长期记忆。</p>
        <Link className="button" to="/assistant/preferences">
          管理 AI 偏好
        </Link>
      </section>
      <section className="settings-card">
        <h2>账号操作</h2>
        <ConfirmButton
          className="danger full"
          title="退出登录"
          message="确认退出登录吗？"
          confirmLabel="确认退出"
          onConfirm={session.logout}
        >
          退出登录
        </ConfirmButton>
        <div className="account-security-actions">
          <ChangePassword />
          <ConfirmButton
            className="account-deactivate"
            title="注销账号"
            message="确认注销账号吗？注销后将无法登录，业务数据保留。以后使用同一邮箱重新注册并验证邮箱，即可恢复原数据。"
            confirmLabel="确认注销"
            onConfirm={session.deactivate}
          >
            注销账号
          </ConfirmButton>
        </div>
      </section>
    </main>
  );
}
