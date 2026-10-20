import Input from "@rc-component/input";
import { useState } from "react";
import type { ReviewItem } from "./types";
const targetLabel: Record<ReviewItem["target_type"], string> = {
  todo: "待办",
  event: "日程",
  checklist: "清单",
  reminder: "提醒",
  document: "档案",
};

export function ReviewCard({
  item,
  busy,
  update,
  selected,
  toggle,
}: {
  item: ReviewItem;
  busy: boolean;
  update: (item: ReviewItem, action: "save" | "accept" | "ignore", title: string) => Promise<void>;
  selected: boolean;
  toggle: () => void;
}) {
  const [title, setTitle] = useState(item.title);
  return (
    <article className="review-action-card">
      <div className="row">
        <input
          autoComplete="off"
          aria-label="选择此项"
          type="checkbox"
          checked={selected}
          onChange={toggle}
        />
        <span className="status-tag">{targetLabel[item.target_type]}</span>
        <span className="confidence">置信度 {Math.round(item.confidence * 100)}%</span>
      </div>
      <label>
        候选标题
        <Input
          autoComplete="off"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={15}
        />
      </label>
      <blockquote>{item.evidence}</blockquote>
      {item.change_kind && (
        <p className="notice">
          识别为
          {item.change_kind === "cancelled"
            ? "取消"
            : item.change_kind === "changed"
              ? "变更"
              : "重复"}
          {item.previous_value ? ` · 原值：${item.previous_value}` : ""}
        </p>
      )}
      <p className="muted small">来源：{item.material_name}</p>
      <div className="review-actions">
        <button disabled={busy} onClick={() => void update(item, "ignore", title)}>
          忽略
        </button>
        <button
          className="confirm-button"
          disabled={busy || !title.trim()}
          onClick={() => void update(item, "accept", title)}
        >
          {busy ? "处理中…" : "接受并创建"}
        </button>
      </div>
    </article>
  );
}
