import Input from "@rc-component/input";
export function MealDraftPreferences({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
}) {
  return (
    <section className="wide-field meal-settings meal-draft-preferences">
      <h2>本餐偏好与限制（可选）</h2>
      <div className="meal-preference-form">
        <label>
          偏好或限制
          <Input
            autoComplete="off"
            maxLength={100}
            placeholder="如：少辣、花生过敏"
            value={value}
            disabled={disabled}
            onChange={(event) => onChange(event.target.value)}
          />
        </label>
      </div>
    </section>
  );
}
