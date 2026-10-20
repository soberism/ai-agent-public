import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { AgentRun } from "./types";

type Props = {
  busy: boolean;
  run: AgentRun;
  onCancel: () => Promise<void>;
  onResume: (actionIds: string[]) => Promise<void>;
};

export function AgentActionPlan({ busy, run, onCancel, onResume }: Props) {
  const selectable = run.actions.filter((action) => action.status === "proposed");
  const waiting = run.status === "waiting";
  const [selected, setSelected] = useState<string[]>([]);

  useEffect(
    () =>
      setSelected(
        run.actions.filter((action) => action.status === "proposed").map((action) => action.id),
      ),
    [run.actions, run.id, run.plan_version],
  );

  return (
    <section className="agent-plan" aria-label={waiting ? "待确认操作" : "执行进度"}>
      <div className="agent-plan-heading">
        <strong>{waiting ? "请确认要执行的操作" : "正在执行操作"}</strong>
        {waiting && (
          <span>
            {selected.length}/{selectable.length} 项已选
          </span>
        )}
      </div>
      <div className="agent-action-list">
        {run.actions.map((action) => {
          const canSelect = waiting && action.status === "proposed";
          const detailUrl = action.result?.items[0]?.url;
          const Item = canSelect ? "label" : "div";
          return (
            <Item className="agent-action" key={action.id}>
              {canSelect && (
                <input
                  type="checkbox"
                  checked={selected.includes(action.id)}
                  disabled={busy}
                  onChange={(event) =>
                    setSelected((current) =>
                      event.target.checked
                        ? [...current, action.id]
                        : current.filter((id) => id !== action.id),
                    )
                  }
                />
              )}
              <span className="agent-action-content">
                <strong>{action.title}</strong>
                {waiting && action.description && (
                  <ActionDescription description={action.description} />
                )}
                {action.status === "completed" && (
                  <small className="agent-action-result">已完成</small>
                )}
                {action.status === "completed" && detailUrl && (
                  <Link className="agent-action-detail" to={detailUrl}>
                    进入详情
                  </Link>
                )}
                {action.error && <small className="agent-action-error">{action.error}</small>}
              </span>
            </Item>
          );
        })}
      </div>
      {waiting && (
        <div className="agent-plan-actions">
          <button type="button" className="button secondary" disabled={busy} onClick={onCancel}>
            取消
          </button>
          <button
            type="button"
            className="button primary"
            disabled={busy || selected.length === 0}
            onClick={() => void onResume(selected)}
          >
            确认
          </button>
        </div>
      )}
    </section>
  );
}

function ActionDescription({ description }: { description: string }) {
  return (
    <span className="agent-action-description">
      {description
        .replace(/^内容：\s*/u, "")
        .split("；")
        .map((part, index) => {
          const separator = part.indexOf("：");
          if (separator < 0) return <span key={index}>{part}</span>;
          return (
            <span className="agent-action-field" key={index}>
              <span className="agent-action-field-label">{part.slice(0, separator)}</span>
              <span className="agent-action-field-value">{part.slice(separator + 1)}</span>
            </span>
          );
        })}
    </span>
  );
}
