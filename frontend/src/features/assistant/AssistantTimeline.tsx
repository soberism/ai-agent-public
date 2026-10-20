import { Fragment } from "react";
import { AgentRunPanel } from "./AgentRunPanel";
import { AssistantReplyView } from "./AssistantReplyView";
import type { AgentRun, AgentSuggestion, ChatEntry } from "./types";

type Props = {
  entries: ChatEntry[];
  busy: boolean;
  run: AgentRun | null;
  pendingRuns: AgentRun[];
  onCancel: (run: AgentRun) => Promise<void>;
  onResume: (run: AgentRun, actionIds: string[]) => Promise<void>;
  onConfirm: (token: string) => Promise<void>;
  onChoose: (suggestion: AgentSuggestion) => void;
};

export function AssistantTimeline({
  entries,
  busy,
  run,
  pendingRuns,
  onCancel,
  onResume,
  onConfirm,
  onChoose,
}: Props) {
  return (
    <>
      {entries.map((entry, index) => {
        if (entry.role === "user")
          return (
            <p className="chat-user" key={index}>
              {entry.message}
            </p>
          );
        const current =
          run?.id === entry.id ? run : pendingRuns.find((item) => item.id === entry.id);
        const hasPlan =
          current &&
          ["waiting", "queued", "running"].includes(current.status) &&
          current.actions.length > 0;
        return (
          <Fragment key={entry.id || index}>
            {!hasPlan && (
              <AssistantReplyView
                reply={entry.reply}
                busy={busy}
                onConfirm={onConfirm}
                onChoose={onChoose}
              />
            )}
            {current && (
              <div className="agent-run-group">
                <AgentRunPanel
                  busy={busy}
                  run={current}
                  onCancel={() => onCancel(current)}
                  onResume={(actionIds) => onResume(current, actionIds)}
                />
              </div>
            )}
          </Fragment>
        );
      })}
      {busy && entries.at(-1)?.role === "user" && (
        <p className="chat-thinking" role="status">
          {run?.progress || "思考中…"}
        </p>
      )}
    </>
  );
}
