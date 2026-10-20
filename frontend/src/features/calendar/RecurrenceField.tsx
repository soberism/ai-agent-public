export function RecurrenceField({
  value,
  update,
}: {
  value: string;
  update: (value: string) => void;
}) {
  return (
    <fieldset className="recurrence-field">
      <legend>重复</legend>
      <div className="recurrence-options">
        {[
          ["none", "不重复"],
          ["daily", "每天"],
          ["weekly", "每周"],
        ].map(([option, label]) => (
          <label key={option}>
            <input
              type="radio"
              name="recurrence"
              value={option}
              checked={value === option}
              onChange={() => update(option)}
            />
            <span>{label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
