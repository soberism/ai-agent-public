import { expect, test } from "@playwright/test";

test("日期时间分步确认，取消保留原值，手机和桌面弹窗不溢出", async ({ page }) => {
  await page.goto("/login");
  await page.evaluate(`(async () => {
    const {default:R} = await import('/node_modules/.vite/deps/react.js');
    const {default:D} = await import('/node_modules/.vite/deps/react-dom_client.js');
    const {PickerInput} = await import('/src/shared/PickerInput.tsx');
    const host = document.createElement('div'); document.body.append(host);
    D.createRoot(host).render(R.createElement('form', {id:'date-proof'}, R.createElement(PickerInput, {type:'datetime-local', name:'appointment', defaultValue:'2026-09-17T09:00', required:true})));
  })()`);
  for (const width of [390, 1280]) {
    await page.setViewportSize({ width, height: 844 });
    await page.locator("#date-proof .picker-trigger").click();
    const bounds = await page.locator("dialog[open]").boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
    await page.screenshot({ path: `/tmp/ai-agent-date-picker-${width}.png` });
    await page.getByRole("button", { name: "关闭选择日期" }).click();
  }
  await page.locator("#date-proof .picker-trigger").click();
  await page.getByRole("button", { name: "2026年9月18日", exact: true }).click();
  await page.getByRole("button", { name: "关闭选择时间" }).click();
  await expect(page.locator("#date-proof .picker-trigger")).toHaveText("2026/09/17 09:00");
  await page.locator("#date-proof .picker-trigger").click();
  await page.getByRole("button", { name: "2026年9月18日", exact: true }).click();
  await page.getByRole("button", { name: "14时", exact: true }).click();
  await page.getByRole("button", { name: "35分", exact: true }).click();
  await page.getByRole("button", { name: "确认时间", exact: true }).click();
  expect(
    await page
      .locator("#date-proof")
      .evaluate((form) => Object.fromEntries(new FormData(form as HTMLFormElement))),
  ).toEqual({ appointment: "2026-09-18T14:35" });
});

test("共享选择器保留选择事件、表单值和重置行为", async ({ page }) => {
  await page.goto("/login");
  await page.evaluate(`(async () => {
    const {default:R} = await import('/node_modules/.vite/deps/react.js');
    const {default:D} = await import('/node_modules/.vite/deps/react-dom_client.js');
    const {Select} = await import('/src/shared/Select.tsx');
    const {PickerInput} = await import('/src/shared/PickerInput.tsx');
    const host = document.createElement('div');
    document.body.append(host);
    D.createRoot(host).render(R.createElement('form', {id:'picker-proof'},
      R.createElement(Select, {name:'status', defaultValue:'a', onChange:e=>host.dataset.status=e.target.value},
        R.createElement('option', {value:'a'}, '已安排'),
        R.createElement('option', {value:'b'}, '已取消')),
      R.createElement(PickerInput, {type:'time', name:'time', defaultValue:'09:37', onChange:e=>host.dataset.time=e.target.value}),
      R.createElement('button', {type:'reset'}, '重置')));
  })()`);
  await page.locator("#picker-proof .picker-trigger").first().click();
  await page.getByRole("button", { name: "已取消" }).click();
  await expect(page.locator("#picker-proof .picker-trigger").first()).toHaveText("已取消");
  await page.locator("#picker-proof .picker-trigger").nth(1).click();
  await page.getByRole("button", { name: "38分", exact: true }).click();
  await page.getByRole("button", { name: "确认时间", exact: true }).click();
  await expect(page.locator("[data-time]")).toHaveAttribute("data-time", "09:38");
  expect(
    await page
      .locator("#picker-proof")
      .evaluate((form) => Object.fromEntries(new FormData(form as HTMLFormElement))),
  ).toEqual({ status: "b", time: "09:38" });
  await page.getByRole("button", { name: "重置", exact: true }).click();
  await expect(page.locator("#picker-proof .picker-trigger").first()).toHaveText("已安排");
  await expect(page.locator("#picker-proof .picker-trigger").nth(1)).toHaveText("09:37");
});
