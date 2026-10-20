import { Fragment } from "react";
import { Link } from "react-router-dom";

const pages: Record<string, string> = {
  "/assistant/preferences": "AI 设置",
  "/voice-memos": "语音备忘",
  "/daily-dump": "随手记",
  "/checklists": "清单",
  "/connections": "连接管理",
  "/documents": "材料管理",
  "/calendar": "日程",
  "/settings": "账号设置",
  "/shopping": "购物清单",
  "/family": "家庭空间",
  "/search": "全局搜索",
  "/review": "计划回顾",
  "/meals": "餐食计划",
  "/todos": "待办",
};

const pageOrBold =
  /\*\*[^*\n]+\*\*|(?<![:/\w])\/(?:assistant\/preferences|voice-memos|daily-dump|checklists|connections|documents|calendar|settings|shopping|family|search|review|meals|todos)(?![\w/-])/g;

function readable(text: string) {
  const parts = [];
  let start = 0;
  for (const match of text.matchAll(pageOrBold)) {
    if (match.index > start) parts.push(text.slice(start, match.index));
    const part = match[0];
    parts.push(
      pages[part] ? (
        <Link key={match.index} to={part}>
          打开{pages[part]}
        </Link>
      ) : (
        <strong key={match.index}>{part.slice(2, -2)}</strong>
      ),
    );
    start = match.index + part.length;
  }
  parts.push(text.slice(start));
  return parts;
}

function sourceUrl(line: string): string | undefined {
  if (!/^https?:\/\/\S+$/i.test(line)) return;
  try {
    const url = new URL(line);
    const host = url.hostname.toLowerCase().replace(/\.$/, "");
    // 只链接完整域名；IP 和本地域名保留为原文。
    if (
      url.username ||
      url.password ||
      !/^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$/i.test(host) ||
      /(?:^|\.)(?:localhost|local|internal|lan|home|test|invalid|onion)$/.test(host)
    )
      return;
    return url.href;
  } catch {
    return;
  }
}

export function AssistantMessageText({ message }: { message: string }) {
  const sourceMarker = "\n\n参考来源：\n";
  const sourceStart = message.lastIndexOf(sourceMarker);
  const body = sourceStart < 0 ? message : message.slice(0, sourceStart + sourceMarker.length);
  const sources = sourceStart < 0 ? "" : message.slice(sourceStart + sourceMarker.length);
  return (
    <p>
      {readable(body)}
      {sources.split("\n").map((line, index) => {
        const href = sourceUrl(line.trim());
        return (
          <Fragment key={index}>
            {index > 0 && "\n"}
            {href ? (
              <a href={href} target="_blank" rel="noopener noreferrer">
                {line}
              </a>
            ) : (
              line
            )}
          </Fragment>
        );
      })}
    </p>
  );
}
