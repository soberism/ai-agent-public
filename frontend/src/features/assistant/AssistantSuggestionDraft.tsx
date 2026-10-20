import type { AgentSuggestion } from "./types";

type Props = { suggestion: AgentSuggestion | null; onCancel: () => void };

export function AssistantSuggestionDraft({ suggestion, onCancel }: Props) {
  if (!suggestion) return null;
  return (
    <div className="assistant-suggestion-selected">
      <span>
        继续操作：{suggestion.label} · {suggestion.target_title}
      </span>
      <button type="button" aria-label="取消快捷操作" onClick={onCancel}>
        ×
      </button>
    </div>
  );
}
