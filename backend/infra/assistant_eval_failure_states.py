"""按本次采集的确切Run ID只读恢复失败前的图状态，不扫描其他会话。"""

import argparse
import json
from pathlib import Path

from langgraph.checkpoint.postgres import PostgresSaver

from backend.core.security import settings
from backend.features.assistant.autonomous_workflow import builder


def recover(files, output):
    assert settings.postgres_db == "ai_agent_test", "只能读取专用测试库"
    records = [
        json.loads(line) for path in files for line in path.read_text().splitlines()
    ]
    recovered = {}
    with PostgresSaver.from_conn_string(settings.checkpoint_url) as saver:
        graph = builder.compile(checkpointer=saver)
        for record in records:
            for index, step in enumerate(record["steps"], 1):
                run = step.get("actual", {})
                if run.get("status") != "failed":
                    continue
                state = graph.get_state({"configurable": {"thread_id": run["id"]}})
                recovered[run["id"]] = {
                    "case_id": record["id"],
                    "step": index,
                    "next_nodes": list(state.next),
                    "trace": {
                        key: state.values.get(key)
                        for key in (
                            "observations",
                            "knowledge",
                            "web_results",
                            "decision",
                            "proposed_actions",
                            "iteration",
                            "claim_retries",
                            "stalled_on",
                        )
                    },
                }
    output.write_text(json.dumps(recovered, ensure_ascii=False, indent=2) + "\n")
    print(f"恢复{len(recovered)}个失败Run的最后图状态")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    recover(args.files, args.output)


if __name__ == "__main__":
    main()
