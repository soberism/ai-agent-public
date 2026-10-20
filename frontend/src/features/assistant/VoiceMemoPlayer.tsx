import { Toast } from "../../shared/Toast";
import { useRef, useState } from "react";
import { messageOf } from "../../shared/api";

const clock = (value: number) => {
  const seconds = Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0;
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
};

export function VoiceMemoPlayer({ src }: { src: string }) {
  const audio = useRef<HTMLAudioElement>(null);
  const discoveringDuration = useRef(false);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [speed, setSpeed] = useState(1);
  const [error, setError] = useState("");
  async function toggle() {
    const player = audio.current;
    if (!player) return;
    setError("");
    try {
      if (player.paused) {
        if (player.error) {
          discoveringDuration.current = false;
          player.load();
          player.playbackRate = speed;
        }
        await player.play();
      } else player.pause();
    } catch (reason) {
      setError(messageOf(reason));
    }
  }
  return (
    <div className="memo-player-wrap">
      <audio
        ref={audio}
        src={src}
        preload="auto"
        onLoadedMetadata={(event) => {
          const player = event.currentTarget;
          if (!Number.isFinite(player.duration)) {
            discoveringDuration.current = true;
            player.currentTime = Number.MAX_SAFE_INTEGER;
          }
        }}
        onSeeked={(event) => {
          if (!discoveringDuration.current) return;
          const player = event.currentTarget;
          setDuration(Number.isFinite(player.duration) ? player.duration : player.currentTime);
          discoveringDuration.current = false;
          player.currentTime = 0;
          setTime(0);
        }}
        onPlay={(event) => {
          document.querySelectorAll("audio").forEach((player) => {
            if (player !== event.currentTarget) player.pause();
          });
          setPlaying(true);
        }}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onTimeUpdate={(event) => {
          if (!discoveringDuration.current) setTime(event.currentTarget.currentTime);
        }}
        onDurationChange={(event) =>
          setDuration(
            Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0,
          )
        }
        onError={() => {
          setPlaying(false);
          setError("录音加载失败，请重试播放");
        }}
      />
      <div className="memo-player">
        <button
          type="button"
          className="memo-play"
          aria-label={playing ? "暂停录音" : "播放录音"}
          onClick={() => void toggle()}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            {playing ? <path d="M8 5v14M16 5v14" /> : <path d="m9 5 10 7-10 7Z" />}
          </svg>
        </button>
        <div className="memo-player-progress">
          <input
            type="range"
            aria-label="录音进度"
            min={0}
            max={duration || 1}
            step={0.1}
            value={Math.min(time, duration || 1)}
            disabled={!duration}
            onChange={(event) => {
              if (audio.current) {
                audio.current.currentTime = Number(event.target.value);
                setTime(Number(event.target.value));
              }
            }}
          />
          <div className="memo-player-time">
            <span>{clock(time)}</span>
            <span>{duration ? clock(duration) : "--:--"}</span>
          </div>
        </div>
        <button
          type="button"
          className="memo-player-speed"
          aria-label={`播放速度 ${speed}倍，点击切换`}
          onClick={() => {
            const speeds = [1, 1.25, 1.5, 2, 3];
            const next = speeds[(speeds.indexOf(speed) + 1) % speeds.length];
            setSpeed(next);
            if (audio.current) audio.current.playbackRate = next;
          }}
        >
          {speed}×
        </button>
      </div>
      <Toast message={error} tone="error" />
    </div>
  );
}
