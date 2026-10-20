type Props = {
  label: string;
  disabled: boolean;
  recording: boolean;
  showLabel: boolean;
  onPress: () => void;
  onRelease: () => void;
};

export function VoicePressButton({
  label,
  disabled,
  recording,
  showLabel,
  onPress,
  onRelease,
}: Props) {
  return (
    <div className="voice-press-control">
      <button
        type="button"
        className={`voice-button ${recording ? "recording" : ""}`}
        disabled={disabled}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          event.preventDefault();
          event.currentTarget.setPointerCapture(event.pointerId);
          onPress();
        }}
        onPointerUp={onRelease}
        onPointerCancel={onRelease}
        onKeyDown={(event) => {
          if (event.repeat || (event.key !== " " && event.key !== "Enter")) return;
          event.preventDefault();
          onPress();
        }}
        onKeyUp={(event) => {
          if (event.key === " " || event.key === "Enter") {
            event.preventDefault();
            onRelease();
          }
        }}
        onContextMenu={(event) => event.preventDefault()}
        aria-label={label}
      >
        <svg aria-hidden="true" viewBox="0 0 24 24">
          {recording ? (
            <rect x="7" y="7" width="10" height="10" rx="2" />
          ) : (
            <>
              <rect x="9" y="3" width="6" height="11" rx="3" />
              <path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8" />
            </>
          )}
        </svg>
        {showLabel && <span>{label}</span>}
      </button>
    </div>
  );
}
