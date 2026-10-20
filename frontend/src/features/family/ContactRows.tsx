import { VisibilityControl } from "../sharing/VisibilityControl";
import type { Contact } from "./types";

export function ContactRows({ contacts }: { contacts: Contact[] }) {
  if (!contacts.length) return <p className="muted">没有找到联系人</p>;
  return (
    <ul className="plain-list">
      {contacts.map((contact) => (
        <li key={contact.id}>
          <strong>{contact.name}</strong>
          <VisibilityControl kind="contact" id={contact.id} />
          <span>
            {[contact.relationship, contact.phone, contact.email].filter(Boolean).join(" · ") ||
              "暂无联系方式"}
          </span>
        </li>
      ))}
    </ul>
  );
}
