import Input from "@rc-component/input";
import { Select } from "../../shared/Select";
import { IncomingInvitations } from "./IncomingInvitations";
import { useToast } from "../../shared/useToast";
import { Toast } from "../../shared/Toast";
import { useCallback, useEffect, useState } from "react";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { Loading } from "../../shared/Loading";
import { PageHeader } from "../../shared/PageHeader";
import "./family.css";
import { FamilyContent } from "./FamilyContent";
import type { HouseholdDetail, HouseholdSummary } from "./types";

export function FamilyPage() {
  const { call } = useSession();
  const { setNotice, toastProps } = useToast();
  const [households, setHouseholds] = useState<HouseholdSummary[]>([]);
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<HouseholdDetail | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const load = useCallback(async () => {
    setError("");
    try {
      setFailed(false);
      const listing = await call<{ items: HouseholdSummary[] }>("/households");
      setHouseholds(listing.items);
      const home = listing.items.find((item) => item.id === selected) ?? listing.items[0];
      setDetail(home ? await call<HouseholdDetail>(`/households/${home.id}`) : null);
    } catch (failure) {
      setFailed(true);
      setError(messageOf(failure));
    } finally {
      setLoaded(true);
    }
  }, [call, selected]);
  useEffect(() => void load(), [load]);

  async function submit(path: string, body: Record<string, string | null>) {
    setError("");
    try {
      await call(path, { method: "POST", body: JSON.stringify(body) });
      await load();
      return true;
    } catch (failure) {
      setError(messageOf(failure));
      return false;
    }
  }
  async function createFamily() {
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      const home = await call<HouseholdSummary>("/households", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      setName("");
      setShowCreate(false);
      setLoaded(false);
      setSelected(home.id);
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setSaving(false);
    }
  }
  async function deleteFamily() {
    if (!detail) return;
    await call(`/households/${detail.id}`, { method: "DELETE" });
    setDetail(null);
    await load();
  }
  async function leaveFamily() {
    if (!detail) return;
    await call(`/households/${detail.id}/leave`, { method: "POST", body: "{}" });
    setDetail(null);
    await load();
  }
  async function saveMember(memberId: string, body: Record<string, unknown>) {
    if (!detail) return false;
    setNotice("");
    setError("");
    try {
      await call(`/households/${detail.id}/members/${memberId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      await load();
      if ("role" in body) setNotice("角色保存成功");
      return true;
    } catch (failure) {
      setError(messageOf(failure));
      return false;
    }
  }

  return (
    <main className="page feature-page family-page">
      <PageHeader title="家庭空间" />
      {loaded && !failed && detail && !showCreate && (
        <section className="family-switcher" aria-label="家庭选择">
          <div className="family-switcher-heading">
            <span>当前家庭</span>
            {!showCreate && (
              <button
                type="button"
                className="text-button family-create-entry"
                onClick={() => setShowCreate(true)}
              >
                <span aria-hidden="true">＋</span> 创建家庭
              </button>
            )}
          </div>
          {households.length > 1 && (
            <Select
              aria-label="当前家庭"
              value={detail.id}
              onChange={(event) => setSelected(event.target.value)}
            >
              {households.map((home) => (
                <option key={home.id} value={home.id}>
                  {home.name}
                </option>
              ))}
            </Select>
          )}
        </section>
      )}
      <IncomingInvitations onAccepted={load} />
      <Toast {...toastProps} />
      {error && <Toast message={error} tone="error" />}
      {!loaded ? (
        <Loading compact />
      ) : failed ? (
        <section className="state compact">
          <p>家庭空间暂时无法加载。</p>
          <button onClick={() => void load()}>重新加载</button>
        </section>
      ) : !detail || showCreate ? (
        <section className="feature-card family-create-card">
          <div>
            <h2>{detail ? "创建家庭" : "建立家庭空间"}</h2>
            <p className="muted">个人内容默认不会共享。</p>
          </div>
          <form
            className="family-create-form"
            autoComplete="off"
            onSubmit={(e) => {
              e.preventDefault();
              void createFamily();
            }}
          >
            <label>
              家庭名称
              <Input
                required
                maxLength={60}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <div className="family-create-actions">
              {detail && (
                <button type="button" disabled={saving} onClick={() => setShowCreate(false)}>
                  取消
                </button>
              )}
              <button className="primary" disabled={saving}>
                {saving ? "创建中…" : "创建家庭"}
              </button>
            </div>
          </form>
        </section>
      ) : (
        <FamilyContent
          detail={detail}
          submit={submit}
          saveMember={saveMember}
          onDelete={deleteFamily}
          onLeave={leaveFamily}
        />
      )}
    </main>
  );
}
