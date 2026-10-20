import { Link } from "react-router-dom";
import { AssistantMessageText } from "./AssistantMessageText";
import { AssistantSuggestions } from "./AssistantSuggestions";
import type { AgentSuggestion, AssistantReply } from "./types";

type Props = {
  reply: AssistantReply;
  busy: boolean;
  onConfirm: (token: string) => Promise<void>;
  onChoose: (suggestion: AgentSuggestion) => void;
};

export function AssistantReplyView({ reply, busy, onConfirm, onChoose }: Props) {
  const navigationUrls = new Set(
    (reply.suggestions || [])
      .filter((suggestion) => suggestion.type === "navigate")
      .map((suggestion) => suggestion.url),
  );
  return (
    <article className="chat-assistant">
      <AssistantMessageText message={reply.message} />
      {reply.items
        .filter((item) => !item.url || !navigationUrls.has(item.url))
        .map((item) => {
          const content = (
            <>
              <strong>{item.title}</strong>
              <span>
                {[item.due_date, item.due_time].filter(Boolean).join(" ") ||
                  (item.kind === "todo" ? "不设截止日期" : item.url ? "打开查看" : "已记录")}
              </span>
            </>
          );
          return item.url ? (
            <Link className="assistant-item" to={item.url} key={`${item.kind}-${item.id}`}>
              {content}
            </Link>
          ) : (
            <div className="assistant-item" key={`${item.kind}-${item.id}`}>
              {content}
            </div>
          );
        })}
      {reply.kind === "confirm" && reply.action_token && (
        <button
          className="text-button assistant-confirm"
          type="button"
          onClick={() => void onConfirm(reply.action_token!)}
          disabled={busy}
        >
          {reply.action_label}
        </button>
      )}
      <AssistantSuggestions
        suggestions={reply.suggestions || []}
        disabled={busy}
        onChoose={onChoose}
      />
    </article>
  );
}
