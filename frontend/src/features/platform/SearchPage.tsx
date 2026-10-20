import Input from "@rc-component/input";
import { shareableKinds } from "../sharing/types";
import { VisibilityControl } from "../sharing/VisibilityControl";
import { SearchMailDialog } from "./SearchMailDialog";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { PageHeader } from "../../shared/PageHeader";
import { Toast } from "../../shared/Toast";
import { useToast } from "../../shared/useToast";

const categories: Record<string, string> = {
  todo: "待办",
  event: "日程",
  checklist: "清单",
  reminder: "提醒",
  contact: "联系人",
  contact_group: "联系人分组",
  household: "家庭",
  profile: "家庭档案",
  pet: "宠物",
  document: "材料",
  material: "材料",
  folder: "材料目录",
  document_review: "文档审核",
  meal: "餐食计划",
  shopping: "购物清单",
  appointment: "医疗预约",
  pantry: "食材库存",
  preference: "饮食偏好",
  voice_memo: "语音备忘",
  memory: "AI 记忆",
  assistant_profile: "AI 自定义偏好",
  mail: "导入邮件",
  email: "邮件通知",
};

type Result = { id: string; kind: string; title: string; detail: string; url: string };

export function SearchPage() {
  const { call } = useSession();
  const [mail, setMail] = useState<Result | null>(null);
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<Result[]>([]);
  const [busy, setBusy] = useState(false);
  const [searched, setSearched] = useState(false);
  const { setNotice, toastProps } = useToast();

  const [composing, setComposing] = useState(false);
  useEffect(() => {
    if (!query.trim() || composing) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const result = await call<{ items: Result[] }>(
          `/hub/search?q=${encodeURIComponent(query.trim())}`,
          { signal: controller.signal },
        );
        if (!controller.signal.aborted) {
          setItems(result.items.filter((item) => item.kind !== "assistant_message"));
          setSearched(true);
        }
      } catch (error) {
        if (!controller.signal.aborted) setNotice(messageOf(error), "error");
      } finally {
        if (!controller.signal.aborted) setBusy(false);
      }
    }, 250);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query, composing, call, setNotice]);

  return (
    <main className="page feature-page global-search-page">
      <PageHeader title="全局搜索" back="/" />
      <div className="global-search-field">
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          aria-hidden="true"
        >
          <circle cx="10.5" cy="10.5" r="6.5" />
          <path d="m16 16 4.5 4.5" />
        </svg>
        <label className="sr-only" htmlFor="global-query">
          搜索内容
        </label>
        <Input
          autoComplete="off"
          id="global-query"
          type="search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setItems([]);
            setSearched(false);
            setBusy(!!e.target.value.trim());
            setNotice("");
          }}
          onCompositionStart={() => setComposing(true)}
          onCompositionEnd={() => setComposing(false)}
          placeholder="搜索事项、录音或材料"
          maxLength={100}
        />
      </div>
      {!query.trim() && (
        <section className="global-search-intro" aria-label="搜索说明">
          <h2>找到生活里的每一件事</h2>
          <p>输入名称、正文或日期关键词，搜索已开放功能中的内容。</p>
          <dl>
            <div>
              <dt>安排与计划</dt>
              <dd>待办、日程、清单及清单项、提醒，包含已完成事项</dd>
            </div>
            <div>
              <dt>餐食与库存</dt>
              <dd>餐食标题、菜品、日期、备注、本餐偏好与食材库存</dd>
            </div>
            <div>
              <dt>材料与目录</dt>
              <dd>文件名称、后缀、目录名称</dd>
            </div>
            <div>
              <dt>记录与 AI</dt>
              <dd>录音与语音备忘、AI 记忆与邮件</dd>
            </div>
          </dl>
          <p className="global-search-hint">只搜索你有权限查看的内容</p>
        </section>
      )}
      {busy && (
        <div className="global-search-status" role="status" aria-live="polite">
          <span className="loading-spinner" aria-hidden="true" />
          <span>搜索中…</span>
        </div>
      )}
      <Toast {...toastProps} />
      {searched && !items.length && (
        <p className="global-search-status" role="status">
          没有找到匹配的事项
        </p>
      )}
      {Object.entries(categories).map(([kind, label]) => {
        const results = items.filter((item) => item.kind === kind);
        return results.length ? (
          <section className="feature-card" key={kind} aria-label={label}>
            <h2>
              {label}（{results.length}）
            </h2>
            <ul className="plain-list">
              {results.map((item) => (
                <li key={item.id}>
                  {["mail", "email"].includes(item.kind) ? (
                    <button className="text-button" type="button" onClick={() => setMail(item)}>
                      <strong>{item.title}</strong>
                    </button>
                  ) : (
                    <Link to={item.url}>
                      <strong>{item.title}</strong>
                    </Link>
                  )}
                  {item.detail && <span>{item.detail}</span>}
                  {item.kind !== "folder" && shareableKinds.includes(item.kind) && (
                    <VisibilityControl
                      kind={item.kind === "document" ? "material" : item.kind}
                      id={item.id}
                    />
                  )}
                </li>
              ))}
            </ul>
          </section>
        ) : null;
      })}
      {mail && (
        <SearchMailDialog
          key={`${mail.kind}-${mail.id}`}
          id={mail.id}
          kind={mail.kind}
          close={() => setMail(null)}
        />
      )}
    </main>
  );
}
