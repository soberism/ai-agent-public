import Input from "@rc-component/input";
import { useSharingEditor } from "../sharing/useSharingEditor";
import { SharingEditor } from "../sharing/SharingEditor";
import { MealDishInput } from "./MealDishInput";
import { useRef, useState } from "react";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { Toast } from "../../shared/Toast";
import { PickerInput } from "../../shared/PickerInput";
import { MealDraftPreferences } from "./MealDraftPreferences";
import { mealTypeLabels, type MealPlan } from "./types";

export function MealEditor({
  meal,
  onSaved,
}: {
  meal: MealPlan;
  onSaved: (meal: MealPlan) => void;
}) {
  const { call } = useSession();
  const sharing = useSharingEditor("meal", meal.id);
  const [dishes, setDishes] = useState(meal.dish.split("、"));
  const [dish, setDish] = useState("");
  const names = [...dishes, ...(!dish.trim() || dishes.includes(dish.trim()) ? [] : [dish.trim()])];
  const combinedDish = names.join("、");
  const [date, setDate] = useState(meal.date ?? "");
  const originalSchedule =
    meal.schedule_text ??
    (meal.date
      ? [
          mealTypeLabels[meal.meal_type ?? ""] ?? meal.meal_type,
          meal.diners != null ? `${meal.diners}人` : "",
        ]
          .filter(Boolean)
          .join(" ")
      : "");
  const [schedule, setSchedule] = useState(originalSchedule);
  const [notes, setNotes] = useState(meal.notes ?? "");
  const originalPreferences = meal.preferences.map((item) => item.label).join("；");
  const [preferences, setPreferences] = useState(originalPreferences);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const pending = useRef(false);
  return (
    <form
      className="compact-form"
      noValidate
      onSubmit={async (event) => {
        event.preventDefault();
        if (pending.current) return;
        if (!names.length) return setError("请添加至少一道菜品");
        if (combinedDish.length > 100) return setError("菜品名称合计最多100字");
        pending.current = true;
        setSaving(true);
        setError("");
        try {
          const updated = await sharing.save(() =>
            call<MealPlan>(`/life/meal-plans/${meal.id}`, {
              method: "PUT",
              body: JSON.stringify({
                dish: combinedDish,
                schedule_text: schedule,
                notes: notes || null,
                date: date || null,
                meal_type: meal.meal_type,
                diners: meal.diners,
                ...(preferences === originalPreferences
                  ? {}
                  : {
                      preferences: preferences.trim()
                        ? [{ label: preferences.trim(), kind: "preference" }]
                        : [],
                    }),
              }),
            }),
          );
          setDishes(updated.dish.split("、"));
          setDish("");
          setDate(updated.date ?? "");
          setNotes(updated.notes ?? "");
          setPreferences(updated.preferences.map((item) => item.label).join("；"));
          onSaved(updated);
        } catch (failure) {
          setError(messageOf(failure));
        } finally {
          pending.current = false;
          setSaving(false);
        }
      }}
    >
      {error && <Toast message={error} tone="error" />}

      <label className="wide-field">
        日期、餐次和人数
        <Input
          autoComplete="off"
          value={schedule}
          maxLength={15}
          disabled={saving || sharing.recovering}
          onChange={(event) => setSchedule(event.target.value)}
        />
      </label>
      <div className="wide-field">
        <label htmlFor="meal-edit-date">日期（可选）</label>
        <PickerInput
          id="meal-edit-date"
          type="date"
          aria-label="餐食日期"
          value={date}
          disabled={saving || sharing.recovering}
          onChange={(event) => setDate(event.target.value)}
        />
      </div>
      <MealDishInput
        dishes={dishes}
        setDishes={setDishes}
        dish={dish}
        setDish={setDish}
        saving={saving || sharing.recovering}
        notify={setError}
      />
      <label className="wide-field">
        备注
        <Input
          autoComplete="off"
          value={notes}
          maxLength={1000}
          disabled={saving || sharing.recovering}
          onChange={(event) => setNotes(event.target.value)}
        />
      </label>
      <MealDraftPreferences
        value={preferences}
        onChange={setPreferences}
        disabled={saving || sharing.recovering}
      />
      <SharingEditor sharing={sharing} disabled={saving || sharing.recovering} />
      <button
        className="primary wide-field"
        disabled={
          saving ||
          (!sharing.recovering &&
            !sharing.changed &&
            combinedDish === meal.dish &&
            date === (meal.date ?? "") &&
            schedule === originalSchedule &&
            notes === (meal.notes ?? "") &&
            preferences === originalPreferences)
        }
      >
        {saving ? "保存中…" : "保存修改"}
      </button>
    </form>
  );
}
