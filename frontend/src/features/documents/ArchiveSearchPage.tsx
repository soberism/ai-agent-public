import Input from "@rc-component/input";
import { VisibilityControl } from "../sharing/VisibilityControl";
import { useState } from "react";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { PageHeader } from "../../shared/PageHeader";
import { Toast } from "../../shared/Toast";
import { useToast } from "../../shared/useToast";

type Item = {
  id: string;
  name: string;
  excerpt: string;
  subject_type: string | null;
  status: string;
};

export function ArchiveSearchPage() {
  const { call } = useSession();
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<Item[]>([]);
  const { setNotice, toastProps } = useToast();
  async function search(event: React.FormEvent) {
    event.preventDefault();
    try {
      const result = await call<Item[]>(`/documents/search?q=${encodeURIComponent(query)}`);
      setItems(result);
      setNotice(result.length ? "" : "没有匹配档案");
    } catch (error) {
      setNotice(messageOf(error), "error");
    }
  }
  async function analyze(id: string) {
    try {
      const result = await call<{ subjects: unknown[]; changes: unknown[] }>(
        `/documents/materials/${id}/analyze`,
        { method: "POST", body: "{}" },
      );
      setNotice(`发现 ${result.subjects.length} 条归属建议、${result.changes.length} 条重复或变化`);
    } catch (error) {
      setNotice(messageOf(error), "error");
    }
  }
  return (
    <main className="page feature-page">
      <PageHeader title="档案检索" back="/documents" />
      <form className="feature-card inline-create" onSubmit={search}>
        <label className="sr-only" htmlFor="archive-query">
          关键词
        </label>
        <Input
          autoComplete="off"
          id="archive-query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          required
          placeholder="文件名、识别文字或来源"
        />
        <button className="primary">检索</button>
      </form>
      <Toast {...toastProps} />
      <section className="feature-card">
        <h2>匹配档案</h2>
        {!items.length ? (
          <p className="muted">输入关键词查找资料</p>
        ) : (
          <ul className="plain-list">
            {items.map((item) => (
              <li key={item.id}>
                <strong>{item.name}</strong>
                <VisibilityControl kind="material" id={item.id} />
                <span>{item.excerpt || "暂无识别文本"}</span>
                <button className="text-button" onClick={() => void analyze(item.id)}>
                  分析归属与变化
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
