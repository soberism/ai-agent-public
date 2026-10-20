import { AgentActionPlan } from "./AgentActionPlan";
import type { AgentRun } from "./types";

type Props = {
  busy: boolean;
  run: AgentRun;
  onCancel: () => Promise<void>;
  onResume: (actionIds: string[]) => Promise<void>;
};

export function AgentRunPanel({ busy, run, onCancel, onResume }: Props) {
  return (
    <>
      {run.sources.length > 0 && (
        <section className="agent-sources" aria-label="回答来源">
          <strong>回答来源</strong>
          <ul>
            {run.sources.map((source, index) => (
              <li key={`${source.title}-${index}`}>
                {source.url ? (
                  <a href={source.url} target="_blank" rel="noreferrer">
                    {source.title}
                  </a>
                ) : (
                  <span>{source.title}</span>
                )}
                {source.excerpt && <small>{source.excerpt}</small>}
              </li>
            ))}
          </ul>
        </section>
      )}
      {["waiting", "queued", "running"].includes(run.status) && run.actions.length > 0 && (
        <AgentActionPlan busy={busy} run={run} onCancel={onCancel} onResume={onResume} />
      )}
    </>
  );
}
