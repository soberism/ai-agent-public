import Input from "@rc-component/input";
import type { ReactNode } from "react";
import { MealDishInput } from "./MealDishInput";
import { Toast } from "../../shared/Toast";
import { useToast } from "../../shared/useToast";
import { useState } from "react";
import { MealDraftPreferences } from "./MealDraftPreferences";
import type { Checklist } from "../checklists/types";
import { Select } from "../../shared/Select";

export function MealForm({
  create,
  visibility,
  saving = false,
  locked = false,
  checklists = [],
}: {
  visibility?: ReactNode;
  create: (path: string, body: Record<string, unknown>) => Promise<boolean>;
  saving?: boolean;
  locked?: boolean;
  checklists?: Checklist[];
}) {
  const { setNotice, toastProps } = useToast();
  const [preferences, setPreferences] = useState("");
  const [schedule, setSchedule] = useState("");
  const [dish, setDish] = useState("");
  const [dishes, setDishes] = useState<string[]>([]);
  return (
    <>
      <Toast {...toastProps} />
      <form
        className="compact-form"
        onInvalid={(event) => {
          event.preventDefault();
          const input = event.target;
          if (
            !(input instanceof HTMLInputElement) ||
            event.currentTarget.querySelector(":invalid") !== input
          )
            return;
          const label = input.labels?.[0]?.textContent?.trim() || "必填内容";
          setNotice(
            input.validity.valueMissing ? `请填写${label}` : `请检查${label}的填写范围`,
            "error",
          );
          input.focus();
        }}
        onSubmit={(e) => {
          e.preventDefault();
          const names = [
            ...dishes,
            ...(!dish.trim() || dishes.includes(dish.trim()) ? [] : [dish.trim()]),
          ];
          if (!names.length) return setNotice("请添加至少一道菜品", "error");
          if (names.join("、").length > 100) return setNotice("菜品名称合计最多100字", "error");
          const data = new FormData(e.currentTarget);
          void create("/life/meal-plans", {
            checklist_id: data.get("checklist_id") || null,
            schedule_text: schedule,
            dish: names.join("、"),
            notes: data.get("notes") || null,
            preferences: preferences.trim()
              ? [{ label: preferences.trim(), kind: "preference" }]
              : [],
          }).then((saved) => saved && setDish(""));
        }}
      >
        <label className="wide-field">
          日期、餐次和人数
          <Input
            disabled={locked}
            autoComplete="off"
            name="meal_schedule"
            placeholder="例如：明晚两个人一起吃饭"
            value={schedule}
            maxLength={15}
            onChange={(event) => setSchedule(event.target.value)}
          />
        </label>
        <MealDishInput
          dishes={dishes}
          setDishes={setDishes}
          dish={dish}
          setDish={setDish}
          saving={saving || locked}
          notify={setNotice}
        />
        <label className="wide-field">
          关联清单
          <Select disabled={locked} name="checklist_id">
            <option value="">自动新建清单</option>
            {checklists.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </Select>
        </label>
        <label className="wide-field">
          备注
          <Input autoComplete="off" name="notes" maxLength={300} />
        </label>
        <MealDraftPreferences
          value={preferences}
          onChange={setPreferences}
          disabled={saving || locked}
        />
        {visibility}
        <button className="primary wide-field" disabled={saving}>
          {saving ? "保存中…" : "保存餐食"}
        </button>
      </form>
    </>
  );
}
