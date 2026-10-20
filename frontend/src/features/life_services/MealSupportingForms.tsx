import Input from "@rc-component/input";
import type { ReactNode } from "react";
import { Toast } from "../../shared/Toast";
import { useToast } from "../../shared/useToast";
import { useState } from "react";

type Create = (path: string, body: Record<string, unknown>) => Promise<boolean>;

export function PreferenceForm({ create, path }: { create: Create; path: string }) {
  const { setNotice, toastProps } = useToast();
  const [label, setLabel] = useState("");
  return (
    <>
      <Toast {...toastProps} />
      <form
        className="inline-fields meal-preference-form"
        onInvalid={(event) => {
          event.preventDefault();
          setNotice("请填写偏好或限制", "error");
          if (event.target instanceof HTMLInputElement) event.target.focus();
        }}
        onSubmit={(e) => {
          e.preventDefault();
          if (!label.trim()) {
            setNotice("请填写偏好或限制", "error");
            return;
          }
          void create(path, { label: label.trim(), kind: "preference" }).then(
            (saved) => saved && setLabel(""),
          );
        }}
      >
        <label>
          偏好或限制
          <Input
            autoComplete="off"
            required
            maxLength={80}
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="少辣、花生过敏"
          />
        </label>
        <button>添加约束</button>
      </form>
    </>
  );
}

export function PantryForm({
  create,
  visibility,
  locked = false,
}: {
  create: Create;
  visibility?: ReactNode;
  locked?: boolean;
}) {
  const [name, setName] = useState("");
  return (
    <form
      className="inline-fields meal-pantry-form"
      onSubmit={(e) => {
        e.preventDefault();
        const data = new FormData(e.currentTarget);
        void create("/life/pantry", {
          name,
          quantity: Number(data.get("quantity")),
          unit: data.get("unit"),
        }).then((saved) => saved && setName(""));
      }}
    >
      <label>
        库存食材
        <Input
          disabled={locked}
          autoComplete="off"
          required
          maxLength={80}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label>
        数量
        <Input
          disabled={locked}
          autoComplete="off"
          name="quantity"
          type="number"
          min="0"
          step="0.1"
          required
        />
      </label>
      <label>
        单位
        <Input disabled={locked} autoComplete="off" name="unit" maxLength={20} placeholder="可选" />
      </label>
      {visibility}
      <button>加入库存</button>
    </form>
  );
}
