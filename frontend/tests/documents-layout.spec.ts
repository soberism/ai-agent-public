import { expect, test } from "@playwright/test";

test("材料管理上传、新建目录、筛选、移动、重命名和删除", async ({ page }, testInfo) => {
  const items: {
    id: string;
    name: string;
    kind: string;
    status: string;
    created_at: string;
    folder_id: string | null;
    error_message: null;
    review_count: number;
  }[] = [];
  const folders = [{ id: "school", name: "学校", count: 0 }];
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let json: unknown = { items: [] };
    if (path === "/api/auth/me" || path === "/api/platform/settings")
      json = { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" };
    if (path === "/api/documents/folders" && request.method() === "POST")
      folders.push({ id: "work", name: request.postDataJSON().name, count: 0 });
    if (path === "/api/documents/folders/work" && request.method() === "DELETE") {
      folders.splice(
        folders.findIndex((folder) => folder.id === "work"),
        1,
      );
      items.forEach((item) => {
        if (item.folder_id === "work") item.folder_id = null;
      });
    }
    if (path === "/api/documents/materials/material-1") {
      if (request.method() === "PATCH") Object.assign(items[0], request.postDataJSON());
      if (request.method() === "DELETE") items.splice(0);
    }
    if (path === "/api/documents/materials") {
      if (request.method() === "POST") {
        expect(request.postData()).toContain('name="recognize"\r\n\r\nfalse');
        expect(request.postData()).toContain('name="folder_id"\r\n\r\nschool');
        items.push({
          id: "material-1",
          name: "学校通知.txt",
          kind: "file",
          status: "uploaded",
          created_at: "2026-09-18T07:00:00Z",
          folder_id: "school",
          error_message: null,
          review_count: 0,
        });
      }
      json = {
        items,
        folders: folders.map((folder) => ({
          ...folder,
          count: items.filter((item) => item.folder_id === folder.id).length,
        })),
      };
    }
    await route.fulfill({ json });
  });
  await page.goto("/documents");
  await expect(page.getByRole("heading", { name: "材料管理" })).toBeVisible();
  await expect(page.getByText("暂无文件", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "所在目录", exact: true }).click();
  await expect(
    page.getByRole("dialog").getByRole("button", { name: "未分类（0）", exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("uncategorized-count.png") });
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "全部文件（0）", exact: true })
    .click();
  await expect(page.getByRole("link", { name: "待审核" })).toHaveCount(0);
  await page.locator(".document-folders > summary").click();
  await page.getByLabel("目录名称").fill("工作");
  await page.getByRole("button", { name: "新建", exact: true }).click();
  await expect(page.locator(".document-folders li").filter({ hasText: "工作" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("directories-expanded.png"), fullPage: true });
  await page.locator(".directory-detail > summary").filter({ hasText: "学校" }).click();
  await expect(page.getByRole("button", { name: "所在目录", exact: true })).toContainText("学校");
  await page.locator(".document-folders > summary").click();
  await page.getByRole("button", { name: "所在目录", exact: true }).click();
  await page.getByRole("button", { name: "学校（0）", exact: true }).click();
  await page.getByRole("button", { name: "上传文件", exact: true }).click();
  await expect(page.getByRole("button", { name: "保存到目录", exact: true })).toContainText("学校");
  await expect(page.getByText("仅保存原文件，单个文件不超过 20 MiB。")).toBeVisible();
  await page.getByLabel("选择文件").setInputFiles({
    name: "学校通知.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("周五家长会"),
  });
  await page.screenshot({ path: testInfo.outputPath("upload-dialog.png"), fullPage: true });
  await page.getByRole("button", { name: "上传保存" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.locator(".document-materials").getByText("学校通知.txt", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("搜索文件", { exact: true }).fill("不存在");
  await expect(page.getByText("暂无文件", { exact: true })).toBeVisible();
  await page.getByLabel("搜索文件", { exact: true }).fill("");
  await page.getByRole("button", { name: "移动 学校通知.txt", exact: true }).click();
  await expect(
    page.getByRole("dialog").getByRole("button", { name: "学校（1 份）", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("directory-option-counts.png"),
    fullPage: true,
  });
  await page.getByRole("dialog").getByRole("button", { name: "工作（0 份）", exact: true }).click();
  await expect(page.getByText("暂无文件", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "所在目录", exact: true }).click();
  await page.getByRole("button", { name: "工作（1）", exact: true }).click();
  await page.getByRole("button", { name: "重命名", exact: true }).click();
  await page.getByLabel("文件名称").fill("会议资料.txt");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(
    page.locator(".document-materials").getByText("会议资料.txt", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "重命名", exact: true }).click();
  await page.getByLabel("文件名称").fill("会议资料.pdf");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByText(/更改文件后缀可能导致文件无法正常打开/)).toBeVisible();
  expect(items[0].name).toBe("会议资料.txt");
  await page.screenshot({
    path: testInfo.outputPath("rename-extension-warning.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "返回修改", exact: true }).click();
  await expect(page.getByLabel("文件名称")).toHaveValue("会议资料.pdf");
  expect(items[0].name).toBe("会议资料.txt");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await page.getByRole("button", { name: "确认更改", exact: true }).click();
  await expect(
    page.locator(".document-materials").getByText("会议资料.pdf", { exact: true }),
  ).toBeVisible();

  await expect(page.getByRole("link", { name: "下载", exact: true })).toHaveAttribute(
    "href",
    /\/download$/,
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: testInfo.outputPath("materials-management.png"), fullPage: true });
  await page.locator(".document-folders > summary").click();
  const directory = page.locator(".directory-detail").filter({ hasText: "工作" });
  await directory.locator("summary").click();
  await expect(directory.locator(".directory-files")).toContainText("会议资料.pdf");
  await directory.locator("summary").click();
  await expect(directory.locator(".directory-content")).not.toBeVisible();
  await directory.locator("summary").click();
  await page.screenshot({
    path: testInfo.outputPath("directory-expanded-files.png"),
    fullPage: true,
  });
  await directory.getByRole("button", { name: "删除目录", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("不会删除文件");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  expect(folders.some((folder) => folder.id === "work")).toBe(true);
  await directory.getByRole("button", { name: "删除目录", exact: true }).click();
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(items[0].folder_id).toBeNull();
  await expect(
    page.locator(".document-materials").getByText("会议资料.pdf", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "删除", exact: true }).click();
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.getByText("暂无文件", { exact: true })).toBeVisible();
});

test("同名目录提示可重复显示，自动消失并位于顶部", async ({ page }, testInfo) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/documents/folders") {
      await route.fulfill({
        status: 409,
        json: { error: { code: "FOLDER_DUPLICATE", message: "目录名称已存在，请换一个名称" } },
      });
      return;
    }
    await route.fulfill({
      json:
        path === "/api/documents/materials"
          ? { items: [], folders: [{ id: "school", name: "学校", count: 0 }] }
          : { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" },
    });
  });
  await page.goto("/documents");
  await page.locator(".document-folders > summary").click();
  const form = await page.locator(".document-folders form").boundingBox();
  const list = await page.locator(".document-folders ul").boundingBox();
  expect(form!.y + form!.height).toBeLessThanOrEqual(list!.y);
  await page.getByLabel("目录名称").fill("学校");
  const submit = page.getByRole("button", { name: "新建", exact: true });
  await submit.click();
  const toast = page.getByRole("alert");
  await expect(toast).toContainText("目录名称已存在");
  expect((await toast.boundingBox())!.y).toBeLessThan(40);
  await page.screenshot({
    path: testInfo.outputPath("directory-duplicate-toast.png"),
    fullPage: true,
  });
  await expect(toast).toHaveCount(0, { timeout: 4500 });
  await submit.click();
  await expect(toast).toBeVisible();
  await page.getByRole("button", { name: "关闭提示" }).click();
  await expect(toast).toHaveCount(0);
  await submit.click();
  await expect(toast).toBeVisible();
});

test("目录选择列表滚动，标题固定可见", async ({ page }, testInfo) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    await route.fulfill({
      json:
        path === "/api/documents/materials"
          ? {
              items: [],
              folders: Array.from({ length: 30 }, (_, index) => ({
                id: `folder-${index}`,
                name: `目录${index + 1}`,
                count: 0,
              })),
            }
          : { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" },
    });
  });
  await page.goto("/documents");
  await page.getByRole("button", { name: "所在目录", exact: true }).click();
  const dialog = page.getByRole("dialog");
  const options = dialog.locator(".picker-options");
  expect(await options.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(
    true,
  );
  await options.hover();
  await page.mouse.wheel(0, 1500);
  await expect.poll(() => options.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  await dialog.getByRole("button", { name: "目录30（0）", exact: true }).scrollIntoViewIfNeeded();
  await expect(dialog.getByRole("heading")).toBeVisible();
  const box = await dialog.boundingBox();
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.y + box!.height).toBeLessThanOrEqual(844);
  await page.screenshot({ path: testInfo.outputPath("directory-scroll.png"), fullPage: true });
  await dialog.getByRole("button", { name: "目录30（0）", exact: true }).click();
  await expect(page.getByRole("button", { name: "所在目录", exact: true })).toContainText("目录30");
});

test("长文件名和文件类型不会撑开卡片", async ({ page }, testInfo) => {
  const names = [
    "【用户中心】菜单管理用例(1).xmind",
    "（实际结算）日清分结算账单-（乌兰察布电业局）_2026-08-17.xlsx",
    "1 (2).jpg",
  ];
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/sharing/states") {
      const keys = new URL(route.request().url()).searchParams.get("resources")!.split(",");
      return route.fulfill({
        json: { states: Object.fromEntries(keys.map((key) => [key, "private"])), editable: keys },
      });
    }
    await route.fulfill({
      json:
        path === "/api/documents/materials"
          ? {
              items: names.map((name, index) => ({
                id: `file-${index}`,
                name,
                kind: "file",
                status: "uploaded",
                created_at: "2026-09-18T07:00:00Z",
                folder_id: "folder",
                error_message: null,
                review_count: 0,
              })),
              folders: [{ id: "folder", name: "123", count: 3 }],
            }
          : { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" },
    });
  });
  await page.goto("/documents");
  await expect(page.locator(".document-materials > li")).toHaveCount(3);
  await expect(page.locator(".material-file-type").first()).toHaveText("XMIND");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: testInfo.outputPath("long-file-cards.png"), fullPage: true });
  await page.locator(".document-folders > summary").click();
  await page.locator(".directory-detail > summary").click();
  await page.screenshot({ path: testInfo.outputPath("long-directory-files.png"), fullPage: true });
});
