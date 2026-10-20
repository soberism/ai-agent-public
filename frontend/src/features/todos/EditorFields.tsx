import Input, { TextArea } from "@rc-component/input";
import { TimeField } from "./TimeField";
import { PickerInput } from "../../shared/PickerInput";
import { codepoints } from "../../shared/text";
import { addDays, nextMonday, todayInZone } from "./rules";
import { useTodoEditor } from "./useTodoEditor";
export function EditorFields({ form }: { form: ReturnType<typeof useTodoEditor> }) {
  const { values, locked, update, fields, validation } = form;
  return (
    <>
      <div>
        <label htmlFor="title">标题</label>
        <Input
          autoComplete="off"
          id="title"
          value={values.title}
          disabled={locked}
          onChange={(event) => update("title", event.target.value)}
          placeholder="例如：买牛奶"
          aria-invalid={!!fields.title}
          aria-describedby="title-help"
        />
        <span id="title-help" className="muted">
          {codepoints(values.title.trim())}/15
        </span>
      </div>
      <div>
        <label htmlFor="description">描述</label>
        <TextArea
          autoComplete="off"
          id="description"

          rows={4}
          value={values.description}
          disabled={locked}
          onChange={(event) => update("description", event.target.value)}
          placeholder="补充需要记住的细节"
          aria-invalid={!!fields.description}
        />
      </div>
      <div>
        <label htmlFor="due-date">截止日期</label>
        <PickerInput
          autoComplete="off"
          id="due-date"
          type="date"
          min="0002-01-01"
          max="9999-12-30"
          value={values.due_date}
          disabled={locked}
          onChange={(event) => update("due_date", event.target.value)}
          aria-invalid={!!(fields.due_date || validation.due_date)}
        />

        <div className="quick-dates">
          {["今天", "明天", "下周一", "不设截止日期"].map((label) => (
            <button
              key={label}
              type="button"
              className="chip"
              disabled={locked}
              onClick={() => {
                const today = todayInZone(new Date());
                update(
                  "due_date",
                  label === "今天"
                    ? today
                    : label === "明天"
                      ? addDays(today, 1)
                      : label === "下周一"
                        ? nextMonday(today)
                        : "",
                );
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <TimeField
        value={values.due_time}
        disabled={locked}
        hasDate={!!values.due_date}
        error={fields.due_time || validation.due_time}
        update={(value) => update("due_time", value)}
      />
    </>
  );
}
