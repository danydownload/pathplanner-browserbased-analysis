const { test, expect } = require('@playwright/test');

const baseURL = process.env.PP_BASE_URL || 'http://127.0.0.1:8765';
const screenshotDir = process.env.PP_SCREENSHOT_DIR || 'artifacts/playwright';

test('map sidebar is slightly wider with compact readable controls', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });

    await page.goto(`${baseURL}/map/`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.sidebar', { timeout: 30000 });
    await page.waitForSelector('#map', { timeout: 30000 });

    const metrics = await page.evaluate(() => {
        const sidebar = document.querySelector('.sidebar');
        const mapColumn = sidebar.nextElementSibling;
        const startInput = document.getElementById('startPoint');
        const startLabel = document.querySelector('label[for="startPoint"]');

        const sidebarRect = sidebar.getBoundingClientRect();
        const mapRect = mapColumn.getBoundingClientRect();

        return {
            inputFontSize: parseFloat(window.getComputedStyle(startInput).fontSize),
            labelFontSize: parseFloat(window.getComputedStyle(startLabel).fontSize),
            mapLeft: mapRect.left,
            pageScrollWidth: document.documentElement.scrollWidth,
            sidebarWidth: sidebarRect.width,
            viewportWidth: window.innerWidth,
        };
    });

    expect(metrics.sidebarWidth).toBeGreaterThanOrEqual(356);
    expect(metrics.sidebarWidth).toBeLessThanOrEqual(364);
    expect(metrics.mapLeft).toBeCloseTo(metrics.sidebarWidth, 1);
    expect(metrics.inputFontSize).toBeLessThanOrEqual(14.5);
    expect(metrics.labelFontSize).toBeLessThanOrEqual(13.5);
    expect(metrics.pageScrollWidth).toBeLessThanOrEqual(metrics.viewportWidth);

    await page.screenshot({ path: `${screenshotDir}/pp-sidebar-after-layout.png`, fullPage: false });
});
