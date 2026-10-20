const sections = [
  { to: "/search", icon: "search", title: "全局搜索", text: "搜索已添加的各类事项" },
  { to: "/checklists", icon: "checklist", title: "清单", text: "准备事项与餐食采购，逐项勾选" },
  { to: "/meals", icon: "meal", title: "餐食计划", text: "家庭偏好、库存与每日餐食" },
  {
    to: "/daily-dump",
    icon: "pencil",
    title: "随手记转待办",
    text: "记下想到的事，确认后转换为待办",
  },
  {
    to: "/review",
    icon: "review",
    title: "计划回顾",
    text: "查看日周概览，处理逾期、未设日期和时间冲突",
  },
  { to: "/family", icon: "family", title: "家庭空间", text: "家庭成员管理" },
  { to: "/contacts", icon: "contacts", title: "联系人", text: "通讯资料与联系人分组" },
  { to: "/documents", icon: "document", title: "材料管理", text: "上传文件、分目录整理" },
  { to: "/archive-search", icon: "archive", title: "档案检索", text: "OCR、归属和变化分析" },
  { to: "/document-review", icon: "approve", title: "待审核", text: "核对提取内容后再写入计划" },
  { to: "/appointments", icon: "medical", title: "医疗安排", text: "应用内准备与时间记录" },
  { to: "/voice-memos", icon: "voice", title: "语音备忘", text: "转写、校对和转换事项" },
  { to: "/notifications", icon: "document", title: "站内通知", text: "查看应用内通知" },
  { to: "/voice-live", icon: "voice", title: "实时语音对话", text: "连续语音输入与通话摘要" },
] as const;

export const unavailable = new Set([
  "/voice-live",
  "/appointments",
  "/contacts",
  "/archive-search",
  "/document-review",
  "/notifications",
]);
export const orderedSections = [...sections].sort(
  (a, b) => Number(unavailable.has(a.to)) - Number(unavailable.has(b.to)),
);
