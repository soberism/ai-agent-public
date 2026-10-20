import { Link } from "react-router-dom";
import type { AgentSuggestion } from "./types";

type Props = {
  suggestions: AgentSuggestion[];
  disabled: boolean;
  onChoose: (suggestion: AgentSuggestion) => void;
};

export function AssistantSuggestions({ suggestions, disabled, onChoose }: Props) {
  const visible = suggestions.filter((suggestion) => suggestion.intent !== "create_reminder");
  if (!visible.length) return null;
  return (
    <div className="assistant-suggestions" aria-label="下一步操作">
      {visible.slice(0, 2).map((suggestion) =>
        suggestion.type === "navigate" && suggestion.url ? (
          <Link className="assistant-suggestion" to={suggestion.url} key={suggestion.id}>
            {suggestion.label}
          </Link>
        ) : (
          <button
            className="assistant-suggestion"
            type="button"
            key={suggestion.id}
            disabled={disabled}
            onClick={() => onChoose(suggestion)}
          >
            {suggestion.label}
          </button>
        ),
      )}
    </div>
  );
}
