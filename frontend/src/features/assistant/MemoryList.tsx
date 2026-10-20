import { TextArea } from "@rc-component/input";
import { ConfirmButton } from "../../shared/ConfirmButton";
import { useState } from "react";
import type { AssistantMemory } from "./types";

type Props = {
  memories: AssistantMemory[];
  busyId: string;
  onUpdate: (id: string, body: { content?: string; enabled?: boolean }) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
};

function MemoryRow({ memory, busyId, onUpdate, onDelete }: Props & { memory: AssistantMemory }) {
  const [editing, setEditing] = useState(false);
  const [content, setContent] = useState(memory.content);
  const busy = busyId === memory.id;

  return (
    <li className="memory-item">
      {editing ? (
        <label>
          记忆内容
          <TextArea
            autoComplete="off"
            value={content}
            maxLength={500}
            onChange={(e) => setContent(e.target.value)}
          />
        </label>
      ) : (
        <p>{memory.content}</p>
      )}
      <div className="memory-meta">
        <span>来源：{memory.source === "user" ? "用户添加" : "AI 建议"}</span>
      </div>
      <div className="memory-actions">
        {editing ? (
          <>
            <button
              type="button"
              disabled={busy || !content.trim()}
              onClick={() =>
                void onUpdate(memory.id, { content: content.trim() })
                  .then(() => setEditing(false))
                  .catch(() => undefined)
              }
            >
              保存
            </button>
            <button type="button" onClick={() => setEditing(false)} disabled={busy}>
              取消
            </button>
          </>
        ) : (
          <button type="button" onClick={() => setEditing(true)} disabled={busy}>
            编辑
          </button>
        )}
        <ConfirmButton
          title="删除记忆"
          message={`确认删除“${memory.content}”吗？删除后无法恢复。`}
          onConfirm={() => onDelete(memory.id)}
          disabled={busy}
        >
          删除
        </ConfirmButton>
      </div>
    </li>
  );
}

export function MemoryList(props: Props) {
  if (!props.memories.length) return <p className="muted">还没有长期记忆。</p>;
  return (
    <ul className="memory-list">
      {props.memories.map((memory) => (
        <MemoryRow key={memory.id} memory={memory} {...props} />
      ))}
    </ul>
  );
}
