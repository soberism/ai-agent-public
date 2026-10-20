import { useLayoutEffect, useRef, useState } from "react";

export function MemoTranscript({ text }: { text: string }) {
  const content = useRef<HTMLParagraphElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [overflowing, setOverflowing] = useState(false);
  useLayoutEffect(() => {
    const element = content.current;
    if (!element) return;
    const measure = () => {
      const lineHeight = Number.parseFloat(getComputedStyle(element).lineHeight);
      setOverflowing(element.scrollHeight > lineHeight * 2 + 1);
    };
    setExpanded(false);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [text]);
  return (
    <div className="memo-transcript">
      <p ref={content} className={expanded ? "expanded" : "collapsed"}>
        {text}
        {overflowing && (
          <button
            type="button"
            aria-label={expanded ? "收起" : "展开"}
            aria-expanded={expanded}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? "收起" : "…展开"}
          </button>
        )}
      </p>
    </div>
  );
}
