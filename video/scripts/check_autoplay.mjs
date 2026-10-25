// Check the landing page video: waits off-screen, plays muted in view, pauses out of view,
// and the sound button unmutes and restarts it.
import { chromium } from "playwright";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.goto("file://" + new URL("../../site/index.html", import.meta.url).pathname);
const state = () => page.evaluate(() => { const v = document.getElementById("demo"); return { paused: v.paused, muted: v.muted, t: +v.currentTime.toFixed(1) }; });
await page.waitForTimeout(1500);
console.log("off-screen on load:", await state());
await page.evaluate(() => document.getElementById("demo").scrollIntoView({ block: "center" }));
await page.waitForTimeout(2000);
console.log("scrolled into view:", await state());
await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
await page.waitForTimeout(800);
console.log("scrolled away:", await state());
await page.evaluate(() => document.getElementById("demo").scrollIntoView({ block: "center" }));
await page.waitForTimeout(500);
await page.click("#sound");
await page.waitForTimeout(800);
console.log("after sound click:", await state());
await browser.close();
