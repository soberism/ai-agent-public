import { useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { NavLink } from "react-router-dom";

export const nav = [
  ["/", "首页", "home"],
  ["/calendar", "日程", "calendar"],
  ["/todos", "待办", "todo"],
  ["/features", "功能", "grid"],
  ["/settings", "我的", "settings"],
] as const;

const navSections: Record<(typeof nav)[number][0], readonly string[]> = {
  "/": ["/"],
  "/calendar": ["/calendar", "/plan"],
  "/todos": ["/todos"],
  "/settings": ["/settings", "/connections", "/notifications", "/assistant/preferences"],
  "/features": [
    "/features",
    "/checklists",
    "/review",
    "/daily-dump",
    "/family",
    "/contacts",
    "/documents",
    "/document-review",
    "/meals",
    "/shopping",
    "/appointments",
    "/search",
    "/archive-search",
    "/voice-memos",
    "/voice-live",
  ],
};

export function activeSection(pathname: string) {
  return (
    (Object.entries(navSections) as [(typeof nav)[number][0], readonly string[]][]).find(
      ([, paths]) =>
        paths.some(
          (path) => pathname === path || (path !== "/" && pathname.startsWith(`${path}/`)),
        ),
    )?.[0] ?? "/features"
  );
}

export function NavIcon({ name }: { name: (typeof nav)[number][2] }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      {name === "home" && (
        <>
          <path d="m3 10 9-7 9 7" />
          <path d="M5 9v11h14V9M9 20v-7h6v7" />
        </>
      )}
      {name === "calendar" && (
        <>
          <rect x="3" y="5" width="18" height="16" rx="3" />
          <path d="M8 3v4M16 3v4M3 10h18" />
          <path d="M8 14h.01M12 14h.01M16 14h.01M8 17h.01M12 17h.01" />
        </>
      )}
      {name === "todo" && (
        <>
          <path d="M7 4H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-2" />
          <path d="m8 12 2.5 2.5L20 5" />
        </>
      )}
      {name === "grid" && (
        <>
          <rect x="3" y="3" width="7" height="7" rx="1" />
          <rect x="14" y="3" width="7" height="7" rx="1" />
          <rect x="3" y="14" width="7" height="7" rx="1" />
          <rect x="14" y="14" width="7" height="7" rx="1" />
        </>
      )}
      {name === "settings" && (
        <>
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1 1.56V21h-4v-.08a1.7 1.7 0 0 0-1-1.56 1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.56-1H3v-4h.08a1.7 1.7 0 0 0 1.56-1 1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.56V3h4v.08a1.7 1.7 0 0 0 1 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9a1.7 1.7 0 0 0 1.56 1H21v4h-.08a1.7 1.7 0 0 0-1.56 1Z" />
        </>
      )}
    </svg>
  );
}

export function DraggableAssistantButton({ hidden, raised }: { hidden: boolean; raised: boolean }) {
  const [position, setPosition] = useState<{ x: number; y: number } | null>(null);
  const drag = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
    moved: boolean;
  } | null>(null);
  const suppressClick = useRef(false);

  function startDrag(event: ReactPointerEvent<HTMLAnchorElement>) {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    drag.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: rect.left,
      originY: rect.top,
      moved: false,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function moveDrag(event: ReactPointerEvent<HTMLAnchorElement>) {
    const current = drag.current;
    if (!current || current.pointerId !== event.pointerId) return;
    const dx = event.clientX - current.startX;
    const dy = event.clientY - current.startY;
    if (Math.hypot(dx, dy) > 4) current.moved = true;
    if (!current.moved) return;
    event.preventDefault();
    const size = event.currentTarget.getBoundingClientRect();
    setPosition({
      x: Math.min(Math.max(8, current.originX + dx), window.innerWidth - size.width - 8),
      y: Math.min(Math.max(8, current.originY + dy), window.innerHeight - size.height - 8),
    });
  }

  function endDrag(event: ReactPointerEvent<HTMLAnchorElement>) {
    const current = drag.current;
    if (!current || current.pointerId !== event.pointerId) return;
    suppressClick.current = current.moved;
    drag.current = null;
    event.currentTarget.releasePointerCapture(event.pointerId);
    window.setTimeout(() => {
      suppressClick.current = false;
    });
  }

  return (
    <NavLink
      className={`assistant-fab${raised ? " raised" : ""}${position ? " dragged" : ""}`}
      style={position ? { left: position.x, top: position.y } : undefined}
      to="/assistant"
      aria-label="打开 AI 对话"
      hidden={hidden}
      draggable={false}
      onDragStart={(event) => event.preventDefault()}
      onPointerDown={startDrag}
      onPointerMove={moveDrag}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onClick={(event) => {
        if (suppressClick.current) event.preventDefault();
      }}
    >
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path
          fill="currentColor"
          d="M12 1.5c1.4 6.2 4.3 9.1 10.5 10.5-6.2 1.4-9.1 4.3-10.5 10.5C10.6 16.3 7.7 13.4 1.5 12 7.7 10.6 10.6 7.7 12 1.5Z"
        />
      </svg>
    </NavLink>
  );
}
