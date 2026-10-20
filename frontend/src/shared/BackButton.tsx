import { useNavigate } from "react-router-dom";

export function BackButton({
  fallback,
  className = "back",
}: {
  fallback: string;
  className?: string;
}) {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      className={className}
      aria-label="返回"
      onClick={() => {
        if (window.history.state?.idx > 0) navigate(-1);
        else navigate(fallback, { replace: true });
      }}
    >
      <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none">
        <path
          d="m15 5-7 7 7 7"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  );
}
