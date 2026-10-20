import { VisibilityControl } from "../sharing/VisibilityControl";
import { MemoTranscript } from "./MemoTranscript";
import { VoiceMemoPlayer } from "./VoiceMemoPlayer";
import { Link } from "react-router-dom";
import { ConfirmButton } from "../../shared/ConfirmButton";
import type { Memo } from "./VoiceMemosPage";
export function VoiceMemoCard({
  item,
  transcribing,
  transcribe,
  convert,
  remove,
}: {
  item: Memo;
  transcribing: string | null;
  transcribe: (item: Memo) => Promise<void>;
  convert: (item: Memo, targetType: "todo" | "event") => Promise<void>;
  remove: (item: Memo) => Promise<void>;
}) {
  return (
    <article id={`voice-memo-${item.id}`} className="card memo-item">
      <header className="memo-item-header">
        <strong>{item.audio_url ? "语音备忘" : "文字备忘"}</strong>
        <time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString("zh-CN")}</time>
      </header>
      {item.transcript && <MemoTranscript text={item.transcript} />}
      {item.audio_url && <VoiceMemoPlayer src={item.audio_url} />}
      <div className="memo-actions">
        <VisibilityControl kind="voice_memo" id={item.id} />
        {!item.transcript && item.audio_url && (
          <button disabled={transcribing !== null} onClick={() => void transcribe(item)}>
            {transcribing === item.id ? "转写中…" : "转文字"}
          </button>
        )}
        {item.target_id ? (
          <Link
            to={
              item.target_type === "event"
                ? `/calendar/${item.target_id}/edit`
                : `/todos/${item.target_id}`
            }
          >
            查看已生成{item.target_type === "event" ? "日程" : "待办"}
          </Link>
        ) : item.transcript ? (
          <>
            <ConfirmButton
              title="转为待办"
              message={
                <>
                  确认将这条语音备忘转为待办？
                  <br />
                  {Array.from(item.transcript).slice(0, 15).join("")}
                </>
              }
              onConfirm={() => convert(item, "todo")}
              className=""
              confirmClassName="primary"
              confirmLabel="确认转换"
            >
              转为待办
            </ConfirmButton>
            <ConfirmButton
              title="转为日程"
              message={
                <>
                  确认将这条语音备忘转为日程？
                  <br />
                  {Array.from(item.transcript).slice(0, 15).join("")}
                </>
              }
              onConfirm={() => convert(item, "event")}
              className=""
              confirmClassName="primary"
              confirmLabel="确认转换"
            >
              转为日程
            </ConfirmButton>
          </>
        ) : null}
        <ConfirmButton
          className="danger memo-delete"
          title="删除语音备忘"
          message="删除后无法恢复，已生成的待办或日程不受影响。"
          onConfirm={() => remove(item)}
        >
          删除
        </ConfirmButton>
      </div>
    </article>
  );
}
