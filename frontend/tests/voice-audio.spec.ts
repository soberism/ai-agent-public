import { expect, test } from "@playwright/test";

test.use({
  permissions: ["microphone"],
  launchOptions: { args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] },
});

test("录音直接保存，可播放、暂停、删除；失败可重新录制", async ({ page }, testInfo) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "vibrate", {
      value: (duration: number) => {
        document.documentElement.dataset.vibration = String(duration);
        return true;
      },
    });
  });
  let uploads = 0;
  let playbackRequests = 0;
  let transcriptionCalls = 0;
  let audio = Buffer.alloc(0);
  let items: {
    id: string;
    transcript: string;
    audio_url: string;
    status: string;
    target_id: null;
    target_type: null;
    created_at: string;
  }[] = [];
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (path === "/api/auth/me" || path === "/api/platform/settings")
      return route.fulfill({
        json: {
          id: "voice-test",
          email: "test@example.com",
          nickname: "测试",
          timezone: "Asia/Shanghai",
        },
      });
    if (path === "/api/assistant/transcriptions") transcriptionCalls++;
    if (path === "/api/assistant/voice-memos/audio") {
      uploads++;
      const body = route.request().postDataJSON();
      expect(body.mime_type).toBe("audio/webm");
      audio = Buffer.from(body.audio_base64, "base64");
      expect(audio.length).toBeGreaterThan(0);
      if (uploads === 1)
        return route.fulfill({
          status: 503,
          json: { error: { message: "保存失败，请重试", code: "SERVICE_UNAVAILABLE" } },
        });
      items = [
        {
          id: "memo-audio",
          transcript: "",
          audio_url: "/api/assistant/voice-memos/memo-audio/audio",
          status: "draft",
          target_id: null,
          target_type: null,
          created_at: "2026-09-18T00:00:00Z",
        },
      ];
      return route.fulfill({ status: 201, json: items[0] });
    }
    if (path === "/api/assistant/voice-memos/memo-audio/convert")
      return route.fulfill({
        status: 503,
        json: { error: { code: "SERVICE_UNAVAILABLE", message: "转换失败，请稍后重试" } },
      });
    if (path === "/api/assistant/voice-memos/memo-audio/transcribe") {
      items[0].transcript =
        "明天下午整理出行用品，记得带上充电器。还要检查证件、雨伞和备用衣物，把需要采购的用品整理成清单。出门之前再确认一次行程和集合时间，以免遗漏重要安排。";
      return route.fulfill({ json: items[0] });
    }
    if (path === "/api/assistant/voice-memos/memo-audio/audio") {
      if (++playbackRequests === 1) return route.fulfill({ status: 503, body: "" });
      const range = route.request().headers().range;
      if (range) {
        const [first, last] = range.slice(6).split("-");
        const start = Number(first);
        const end = last ? Math.min(Number(last), audio.length - 1) : audio.length - 1;
        return route.fulfill({
          status: 206,
          contentType: "audio/webm",
          headers: {
            "Accept-Ranges": "bytes",
            "Content-Range": `bytes ${start}-${end}/${audio.length}`,
          },
          body: audio.subarray(start, end + 1),
        });
      }
      return route.fulfill({
        contentType: "audio/webm",
        headers: { "Accept-Ranges": "bytes" },
        body: audio,
      });
    }
    if (path === "/api/assistant/voice-memos/memo-audio" && method === "DELETE") {
      items = [];
      return route.fulfill({ status: 204 });
    }
    if (path === "/api/sharing/states")
      return route.fulfill({
        json: {
          states: { "voice_memo:memo-audio": "private" },
          editable: ["voice_memo:memo-audio"],
        },
      });
    if (path === "/api/assistant/voice-memos") return route.fulfill({ json: items });
    return route.fulfill({ json: {} });
  });
  await page.goto("/voice-memos");
  const button = page.getByRole("button", { name: "按住说话" });
  await button.hover();
  await page.mouse.down();
  await expect(page.getByRole("button", { name: "松开结束录音" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-vibration", "300");
  await page.waitForTimeout(2500); // 生成有实际时长的浏览器测试录音。
  await page.mouse.up();
  await expect(page.getByText("保存失败，请重试", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "按住说话" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "重试保存" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "放弃录音" })).toHaveCount(0);
  await page.getByRole("button", { name: "按住说话" }).hover();
  await page.mouse.down();
  await expect(page.getByRole("button", { name: "松开结束录音" })).toBeVisible();
  await page.waitForTimeout(2500);
  await page.mouse.up();
  await expect(page.locator("audio")).toHaveCount(1);
  await expect(page.locator(".memo-recorder .sharing-editor")).toHaveCount(0);
  await expect(
    page.locator(".memo-item").getByRole("button", { name: "自己可见", exact: true }),
  ).toBeVisible();
  expect(transcriptionCalls).toBe(0);
  await expect(page.getByRole("button", { name: "转文字", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "转为待办" })).toHaveCount(0);
  await expect(page.getByText("录音加载失败，请重试播放", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "播放录音" }).click();
  await expect(page.getByRole("button", { name: "暂停录音" })).toBeVisible();
  expect(await page.locator("audio").evaluate((element: HTMLAudioElement) => element.paused)).toBe(
    false,
  );
  await page.getByRole("button", { name: "暂停录音" }).click();
  expect(await page.locator("audio").evaluate((element: HTMLAudioElement) => element.paused)).toBe(
    true,
  );
  for (const rate of [1.25, 1.5, 2, 3, 1, 1.25, 1.5]) {
    await page.getByRole("button", { name: /^播放速度/ }).click();
    await expect(page.getByRole("button", { name: /^播放速度/ })).toHaveText(`${rate}×`);
    expect(
      await page.locator("audio").evaluate((element: HTMLAudioElement) => element.playbackRate),
    ).toBe(rate);
  }
  expect(
    await page.locator("audio").evaluate((element: HTMLAudioElement) => element.playbackRate),
  ).toBe(1.5);
  const progress = page.getByRole("slider", { name: "录音进度" });
  await expect(progress).toBeEnabled();
  const box = await progress.boundingBox();
  await page.mouse.move(box!.x + 8, box!.y + box!.height / 2);
  await page.mouse.down();
  await page.mouse.move(box!.x + box!.width * 0.65, box!.y + box!.height / 2, { steps: 8 });
  await page.mouse.up();
  await expect
    .poll(() => page.locator("audio").evaluate((element: HTMLAudioElement) => element.currentTime))
    .toBeGreaterThan(1);
  expect(await page.locator("audio").evaluate((element: HTMLAudioElement) => element.paused)).toBe(
    true,
  );
  await expect(page.getByRole("button", { name: "按住说话" })).toBeEnabled();
  expect((await page.locator(".memo-item").boundingBox())!.height).toBeLessThan(170);
  await page.screenshot({ path: testInfo.outputPath("voice-audio-mobile.png"), fullPage: true });
  await page.getByRole("button", { name: "转文字", exact: true }).click();
  await expect(page.getByRole("button", { name: "转为待办" })).toBeVisible();
  await page.getByRole("button", { name: "展开", exact: true }).click();
  await expect(page.getByRole("button", { name: "收起", exact: true })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
  await page.getByRole("button", { name: "收起", exact: true }).click();
  await expect(page.getByRole("button", { name: "展开", exact: true })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  await page.screenshot({
    path: testInfo.outputPath("voice-audio-transcript-mobile.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({
    path: testInfo.outputPath("voice-audio-transcript-desktop.png"),
    fullPage: true,
  });
  for (const label of ["待办", "日程"]) {
    await page.getByRole("button", { name: `转为${label}`, exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(
      dialog.getByText(`确认将这条语音备忘转为${label}？`, { exact: false }),
    ).toBeVisible();
    await dialog.getByRole("button", { name: "取消", exact: true }).click();
    await expect(dialog).toHaveCount(0);
  }
  await page.getByRole("button", { name: "转为待办", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "确认转换", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByText("转换失败，请稍后重试", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("voice-convert-dialog.png"), fullPage: true });
  await page.getByRole("dialog").getByRole("button", { name: "取消", exact: true }).click();
  await page.getByRole("button", { name: "删除", exact: true }).click();
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.locator("audio")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "还没有备忘" })).toBeVisible();
});
