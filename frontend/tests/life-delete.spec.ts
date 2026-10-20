import { expect, test } from "@playwright/test";
for (const kind of ["meal", "shopping"])
  for (const detail of [false, true]) {
    test(`${kind} ${detail ? "详情" : "列表"}删除`, async ({ page }) => {
      let recreated = false;
      let deleted = false,
        writes = 0;
      const meal = {
        id: "meal-1",
        dish: "番茄炒蛋",
        date: "2026-09-20",
        meal_type: "dinner",
        diners: 2,
        notes: "",
        preferences: [],
        calendar_url: null,
        shopping_url: "/shopping/list-1",
      };
      const list = {
        id: "list-1",
        title: "晚餐采购",
        meal_id: "meal-1",
        items: [],
        status: "draft",
        checklist_url: null,
      };
      await page.route("**/api/**", async (route) => {
        const req = route.request(),
          path = new URL(req.url()).pathname;
        const json = (body: unknown) => route.fulfill({ json: body });
        if (path === "/api/auth/me")
          return json({ id: "user-1", email: "demo@example.com", timezone: "Asia/Shanghai" });
        if (req.method() === "DELETE") {
          writes++;
          if (writes === 1)
            return route.fulfill({
              status: 500,
              json: { error: { code: "FAILED", message: "删除失败，请重试" } },
            });
          deleted = true;
          return route.fulfill({ status: 204 });
        }
        if (path === "/api/life/meal-plans")
          return json({
            items:
              deleted && kind === "meal"
                ? []
                : [
                    {
                      ...meal,
                      shopping_url:
                        deleted && kind === "shopping" && !recreated ? null : meal.shopping_url,
                    },
                  ],
            preferences: [],
            pantry: [],
          });
        if (path === "/api/life/meal-plans/meal-1")
          return json({
            ...meal,
            shopping_url: deleted && kind === "shopping" && !recreated ? null : meal.shopping_url,
          });
        if (path === "/api/life/shopping-lists/overview")
          return json({ items: deleted && kind === "shopping" ? [] : [list] });
        if (path === "/api/life/shopping-lists" && req.method() === "GET") {
          expect(new URL(req.url()).searchParams.get("meal_id")).toBe(meal.id);
          recreated = true;
          return json(list);
        }
        if (path === "/api/life/shopping-lists/list-1") return json(list);
        return json({ items: [], delivery: false, payment: false });
      });
      const base = kind === "meal" ? "/meals" : "/checklists";
      const name =
        kind === "meal"
          ? "删除餐食计划 番茄炒蛋"
          : detail
            ? "删除购物清单 晚餐采购"
            : "删除清单：晚餐采购";
      await page.goto(detail ? `${base}/${kind === "meal" ? "meal-1" : "shopping/list-1"}` : base);
      await page.getByRole("button", { name, exact: true }).click();
      await page.getByRole("button", { name: "取消", exact: true }).click();
      expect(writes).toBe(0);
      await page.getByRole("button", { name, exact: true }).click();
      await page.getByRole("button", { name: "确认删除", exact: true }).click();
      await expect(page.getByRole("alert").locator("span")).toHaveText("删除失败，请重试");
      await page.screenshot({ path: `test-results/${kind}-delete-${detail}.png`, fullPage: true });
      await page.getByRole("button", { name: "确认删除", exact: true }).click();
      await expect(page).toHaveURL(new RegExp(`${base}$`));
      await expect(page.getByRole("button", { name, exact: true })).toHaveCount(0);
      await page.reload();
      await expect(page.getByRole("button", { name, exact: true })).toHaveCount(0);
      expect(writes).toBe(2);
      if (kind === "shopping") {
        await page.goto(detail ? "/meals/meal-1" : "/meals");
        await expect(page.getByRole("link", { name: "创建购物清单", exact: true })).toBeVisible();
        await page.screenshot({
          path: `test-results/meal-create-shopping-${detail}.png`,
          fullPage: true,
        });
        await page.getByRole("link", { name: "创建购物清单", exact: true }).click();
        await expect(page).toHaveURL(/shopping\?meal_id=meal-1$/);
        await expect(page.getByRole("heading", { name: "晚餐采购", exact: true })).toBeVisible();
        expect(recreated).toBe(true);
        await page.goto(detail ? "/meals/meal-1" : "/meals");
        await expect(
          page.getByRole("link", { name: detail ? "查看购物清单" : "购物清单", exact: true }),
        ).toHaveAttribute("href", "/shopping/list-1");
        await expect(page.getByRole("link", { name: "创建购物清单", exact: true })).toHaveCount(0);
      } else {
        await page.goto("/shopping/list-1");
        await expect(page.getByRole("heading", { name: "晚餐采购", exact: true })).toBeVisible();
      }
    });
  }
