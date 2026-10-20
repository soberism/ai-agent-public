import { encode } from "./audio";
import { Toast } from "../../shared/Toast";
import { useEffect, useRef, useState } from "react";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { VoicePressButton } from "./VoicePressButton";

type Props = {
  disabled: boolean;
  showLabel?: boolean;
  onRecorded?: (audio: Blob, mimeType: string) => Promise<void>;
  onTranscribed?: (message: string) => void;
  onTranscribingChange?: (transcribing: boolean) => void;
  onRecordingChange?: (recording: boolean) => void;
  onSend?: (message: string) => void;
};

export function VoiceDraft({
  disabled,
  showLabel = false,
  onRecorded,
  onTranscribed,
  onTranscribingChange,
  onRecordingChange,
  onSend,
}: Props) {
  const { call } = useSession();
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const transcription = useRef(Promise.resolve());
  const failed = useRef(false);
  const pressed = useRef(false);
  const transcript = useRef("");
  const [status, setStatus] = useState<"idle" | "recording" | "transcribing">("idle");
  const [error, setError] = useState("");

  useEffect(() => () => stream.current?.getTracks().forEach((track) => track.stop()), []);
  useEffect(() => {
    if (!error) return;
    const timeout = window.setTimeout(() => setError(""), 3000);
    return () => window.clearTimeout(timeout);
  }, [error]);

  async function transcribe(blob: Blob, mimeType: string) {
    if (!blob.size) return setError("没有录到声音，请重试");
    try {
      const result = await call<{ transcript: string }>("/assistant/transcriptions", {
        method: "POST",
        body: JSON.stringify({ audio_base64: await encode(blob), mime_type: mimeType }),
      });
      transcript.current = [transcript.current, result.transcript].filter(Boolean).join(" ");
    } catch (failure) {
      failed.current = true;
      setError(messageOf(failure));
    }
  }

  async function start() {
    if (recorder.current?.state === "recording") return;
    setError("");
    transcript.current = "";
    if (!window.isSecureContext) {
      setError("语音录制需要 HTTPS 安全连接");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("当前浏览器不支持语音录制");
      return;
    }
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = ["audio/webm", "audio/mp4", "audio/ogg"].find((type) =>
        MediaRecorder.isTypeSupported(type),
      );
      if (!mimeType) {
        stream.current.getTracks().forEach((track) => track.stop());
        stream.current = null;
        setError("当前浏览器不支持可转写的录音格式");
        return;
      }
      const next = new MediaRecorder(stream.current, { mimeType });
      recorder.current = next;
      const chunks: Blob[] = [];
      transcription.current = Promise.resolve();
      failed.current = false;
      next.ondataavailable = (event) => {
        if (!event.data.size) return;
        chunks.push(event.data);
      };
      next.onstop = () => {
        stream.current?.getTracks().forEach((track) => track.stop());
        stream.current = null;
        const audio = new Blob(chunks, { type: mimeType });
        transcription.current = onRecorded
          ? onRecorded(audio, mimeType).catch(() => {
              failed.current = true;
            })
          : transcribe(audio, mimeType);
        void transcription.current.finally(() => {
          if (!failed.current && transcript.current)
            (onTranscribed ?? onSend)?.(transcript.current);
          if (!onRecorded && !failed.current && !transcript.current)
            setError("没有识别到语音，请重试");
          setStatus("idle");
          onTranscribingChange?.(false);
        });
      };
      next.start();
      setStatus("recording");
      onRecordingChange?.(true);
      if (!pressed.current) stop();
    } catch (failure) {
      setError(
        failure instanceof DOMException && failure.name === "NotAllowedError"
          ? "请在浏览器设置中允许麦克风权限"
          : "无法使用麦克风，请稍后重试",
      );
    }
  }

  function stop() {
    if (recorder.current?.state !== "recording") return;
    onRecordingChange?.(false);
    setStatus("transcribing");
    onTranscribingChange?.(true);
    recorder.current?.stop();
  }

  function press() {
    pressed.current = true;
    navigator.vibrate?.(300);
    void start();
  }

  function release() {
    pressed.current = false;
    stop();
  }

  const actionLabel =
    status === "recording"
      ? "松开结束录音"
      : status === "transcribing"
        ? onRecorded
          ? "录音保存中"
          : "语音转换中"
        : "按住说话";

  return (
    <div className="voice-entry">
      <VoicePressButton
        label={actionLabel}
        disabled={disabled || status === "transcribing"}
        recording={status === "recording"}
        showLabel={showLabel}
        onPress={press}
        onRelease={release}
      />
      <Toast message={error} tone="error" />
    </div>
  );
}
