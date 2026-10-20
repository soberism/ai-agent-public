const prompts = [
  "查看我今天的待办",
  "查看今天的日程",
  "创建旅行准备清单",
  "查看餐食计划",
  "回顾本周的计划",
  "查看我的材料",
  "查看语音备忘",
  "查看家庭成员",
];

export function AssistantEmpty({
  disabled,
  onSend,
}: {
  disabled: boolean;
  onSend: (message: string) => void;
}) {
  return (
    <section className="assistant-empty">
      <span aria-hidden="true">✦</span>
      <h2>今天，有什么想交给我？</h2>
      <p>
        我可以帮你处理待办、日程、清单和餐食，整理随手记、回顾计划，也能查询材料、语音备忘和家庭空间。修改前会先请你确认。
      </p>
      <div className="assistant-prompts">
        {prompts.map((prompt) => (
          <button key={prompt} type="button" onClick={() => onSend(prompt)} disabled={disabled}>
            {prompt}
          </button>
        ))}
      </div>
    </section>
  );
}
