import { chromium } from "playwright-core";
const b = await chromium.launch({ channel: "msedge", headless: true });
for (const width of [1024, 1280, 1440, 1920]) {
  const p = await (await b.newContext({ viewport: { width, height: 900 } })).newPage();
  await p.goto("http://localhost:1421"); await p.waitForLoadState("networkidle");
  await p.waitForTimeout(500);
  await fetch("http://localhost:8010/telemetry/pause", { method: "POST" }); await new Promise((r) => setTimeout(r, 2500));
  const sw = await p.evaluate(() => document.documentElement.scrollWidth);
  console.log(width, "scrollWidth", sw, sw > width ? "OVERFLOW" : "ok");
  if (width === 1280 || width === 1024) await p.screenshot({ path: `shots/8-ground-${width}-link-down.png` });
  await fetch("http://localhost:8010/telemetry/resume", { method: "POST" });
}
await b.close();
