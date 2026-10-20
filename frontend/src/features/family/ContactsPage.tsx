import Input from "@rc-component/input";
import { ContactRows } from "./ContactRows";
import { useSharingEditor } from "../sharing/useSharingEditor";
import { SharingEditor } from "../sharing/SharingEditor";
import { VisibilityControl } from "../sharing/VisibilityControl";
import { uncheckedFirst } from "../../shared/uncheckedFirst";
import { Toast } from "../../shared/Toast";
import { useCallback, useEffect, useState } from "react";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { Loading } from "../../shared/Loading";
import { PageHeader } from "../../shared/PageHeader";
import type { Contact, ContactGroup } from "./types";

export function ContactsPage() {
  const { call } = useSession();
  const contactSharing = useSharingEditor("contact");
  const groupSharing = useSharingEditor("contact_group");
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [groups, setGroups] = useState<ContactGroup[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const load = useCallback(async () => {
    try {
      const [contactData, groupData] = await Promise.all([
        call<{ items: Contact[] }>(`/contacts?q=${encodeURIComponent(query)}`),
        call<{ items: ContactGroup[] }>("/contact-groups"),
      ]);
      setContacts(contactData.items);
      setGroups(groupData.items);
      setError("");
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setLoaded(true);
    }
  }, [call, query]);
  useEffect(() => void load(), [load]);

  async function create(path: string, body: Record<string, unknown>, form: HTMLFormElement) {
    try {
      const sharing = path === "/contacts" ? contactSharing : groupSharing;
      await sharing.save(() =>
        call<{ id: string }>(path, { method: "POST", body: JSON.stringify(body) }),
      );
      sharing.reset();
      form.reset();
      if (path === "/contact-groups") setSelected([]);
      await load();
    } catch (failure) {
      setError(messageOf(failure));
    }
  }

  return (
    <main className="page feature-page">
      <PageHeader title="联系人" />
      <p className="boundary-note">联系人只是通讯资料，不会自动获得家庭或文档访问权限。</p>
      {error && <Toast message={error} tone="error" />}
      <label>
        搜索联系人
        <Input
          autoComplete="off"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>
      {!loaded ? (
        <Loading compact />
      ) : (
        <section className="feature-card">
          <h2>联系人</h2>
          <ContactRows contacts={contacts} />
        </section>
      )}
      <section className="feature-card">
        <h2>添加联系人</h2>
        <form
          className="compact-form"
          onSubmit={(e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            void create(
              "/contacts",
              {
                name: data.get("name"),
                relationship: data.get("relationship") || "其他",
                phone: data.get("phone") || null,
                email: data.get("email") || null,
              },
              e.currentTarget,
            );
          }}
        >
          <label>
            姓名
            <Input
              disabled={contactSharing.recovering}
              autoComplete="off"
              name="name"
              required
              maxLength={60}
            />
          </label>
          <label>
            关系
            <Input
              disabled={contactSharing.recovering}
              autoComplete="off"
              name="relationship"
              maxLength={40}
            />
          </label>
          <label>
            手机号
            <Input
              disabled={contactSharing.recovering}
              autoComplete="off"
              name="phone"
              inputMode="tel"
            />
          </label>
          <label>
            邮箱
            <Input
              disabled={contactSharing.recovering}
              autoComplete="off"
              name="email"
              type="email"
            />
          </label>
          <SharingEditor sharing={contactSharing} />
          <button className="primary">保存联系人</button>
        </form>
      </section>
      <section className="feature-card">
        <h2>分组</h2>
        <ul className="plain-list">
          {groups.map((group) => (
            <li key={group.id}>
              <VisibilityControl kind="contact_group" id={group.id} />
              {group.name} · {group.contact_ids.length} 人
            </li>
          ))}
        </ul>
        <form
          className="compact-form"
          onSubmit={(e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            void create(
              "/contact-groups",
              { name: data.get("name"), contact_ids: data.getAll("contact_ids") },
              e.currentTarget,
            );
          }}
        >
          <label>
            分组名称
            <Input
              disabled={groupSharing.recovering}
              autoComplete="off"
              name="name"
              required
              maxLength={40}
            />
          </label>
          <fieldset>
            <legend>选择联系人</legend>
            {uncheckedFirst(contacts, (contact) => selected.includes(contact.id)).map((contact) => (
              <label className="check-row" key={contact.id}>
                <input
                  disabled={groupSharing.recovering}
                  autoComplete="off"
                  type="checkbox"
                  name="contact_ids"
                  value={contact.id}
                  checked={selected.includes(contact.id)}
                  onChange={(event) =>
                    setSelected((current) =>
                      event.target.checked
                        ? [...current, contact.id]
                        : current.filter((id) => id !== contact.id),
                    )
                  }
                />
                {contact.name}
              </label>
            ))}
          </fieldset>
          <SharingEditor sharing={groupSharing} />
          <button>创建分组</button>
        </form>
      </section>
    </main>
  );
}
