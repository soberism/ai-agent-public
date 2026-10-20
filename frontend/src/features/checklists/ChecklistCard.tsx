import { Link } from "react-router-dom";
import { ConfirmButton } from "../../shared/ConfirmButton";
import { VisibilityControl } from "../sharing/VisibilityControl";
import type { Checklist } from "./types";

export function ChecklistCard({
  item,
  duplicating,
  duplicate,
  remove,
}: {
  item: Checklist;
  duplicating: string | null;
  duplicate: (id: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
}) {
  return (
    <li>
      <Link to={`/checklists/${item.id}`}>
        <strong className="checklist-name">
          {item.title}
          {item.pinned && <span className="checklist-pin">置顶</span>}
        </strong>
        <span>
          {item.completed_count}/{item.total_count} 已完成
        </span>
      </Link>
      <div className="checklist-card-actions">
        <VisibilityControl kind="checklist" id={item.id} />
        <button
          className="text-button checklist-reuse"
          aria-label={`复用${item.title}`}
          disabled={duplicating !== null}
          onClick={() => void duplicate(item.id)}
        >
          {duplicating === item.id ? "复用中…" : "复用"}
        </button>
        <ConfirmButton
          className="text-button checklist-delete"
          ariaLabel={`删除清单：${item.title}`}
          title="删除清单"
          message={`确认删除“${item.title}”及其中的清单项吗？删除后无法恢复。`}
          onConfirm={() => remove(item.id)}
        >
          删除
        </ConfirmButton>
      </div>
    </li>
  );
}
