import { useCallback, useEffect, useRef, useState } from "react";
import type { AnimationEvent } from "react";
import { useNavigate } from "react-router-dom";
import { usePlatform } from "../platform/AppShell";

export function useAssistantClose() {
  const navigate = useNavigate();
  const { assistantReturnTo } = usePlatform();
  const pageRef = useRef<HTMLElement>(null);
  const finished = useRef(false);
  const [closing, setClosing] = useState(false);

  const finishClose = useCallback(() => {
    if (finished.current) return;
    finished.current = true;
    navigate(assistantReturnTo, { replace: true });
  }, [assistantReturnTo, navigate]);

  useEffect(() => {
    if (!closing) return;
    const timer = window.setTimeout(finishClose, 350);
    return () => window.clearTimeout(timer);
  }, [closing, finishClose]);

  function close() {
    if (closing) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      finishClose();
      return;
    }
    const page = pageRef.current;
    if (page) page.style.setProperty("--assistant-exit-from", getComputedStyle(page).transform);
    setClosing(true);
  }

  function onAnimationEnd(event: AnimationEvent<HTMLElement>) {
    if (
      closing &&
      event.target === event.currentTarget &&
      event.animationName === "assistant-lower"
    )
      finishClose();
  }

  return { closing, close, onAnimationEnd, pageRef };
}
