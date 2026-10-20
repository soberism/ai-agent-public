import Input from "@rc-component/input";
export function MealDishInput({
  dishes,
  setDishes,
  dish,
  setDish,
  saving,
  notify,
}: {
  dishes: string[];
  setDishes: (dishes: string[]) => void;
  dish: string;
  setDish: (dish: string) => void;
  saving: boolean;
  notify: (message: string, tone: "error") => void;
}) {
  function addDish() {
    const value = dish.trim();
    if (!value) return notify("请填写菜品名称", "error");
    if (dishes.includes(value)) return notify("已添加该菜品", "error");
    if ([...dishes, value].join("、").length > 100) return notify("菜品名称合计最多100字", "error");
    setDishes([...dishes, value]);
    setDish("");
  }
  return (
    <div className="wide-field meal-dishes">
      <label htmlFor="meal-dish">菜品</label>
      {dishes.length > 0 && (
        <ul className="meal-dish-items">
          {dishes.map((name) => (
            <li className="chip" key={name}>
              <span>{name}</span>
              <button
                type="button"
                className="icon-button"
                aria-label={`移除菜品 ${name}`}
                disabled={saving}
                onClick={() => setDishes(dishes.filter((item) => item !== name))}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    d="m6 6 12 12M18 6 6 18"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                  />
                </svg>
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="inline-create">
        <Input
          id="meal-dish"
          autoComplete="off"
          maxLength={100}
          placeholder="例如：番茄炒蛋"
          value={dish}
          disabled={saving}
          onChange={(event) => setDish(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              addDish();
            }
          }}
        />
        <button type="button" disabled={saving} onClick={addDish}>
          添加菜品
        </button>
      </div>
    </div>
  );
}
