// Screenshot the landing page at desktop and phone widths: node scripts/shoot.mjs <out-dir>
import { chromium } from "playwright";
const out = process.argv[2];
const browser = await chromium.launch();
for (const [name, width, height, scheme] of [["desktop", 1280, 900, "light"], ["phone", 390, 844, "light"], ["dark", 1280, 900, "dark"]]) {
  const page = await browser.newPage({ viewport: { width, height }, colorScheme: scheme });
  await page.goto("file://" + new URL("../../site/index.html", import.meta.url).pathname);
  await page.screenshot({ path: `${out}/site-${name}.png`, fullPage: name !== "dark" });
}
await browser.close();
