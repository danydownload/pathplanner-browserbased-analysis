const { test, expect } = require('@playwright/test');

const baseURL = process.env.PP_BASE_URL || 'http://localhost:8024';
const screenshotDir = process.env.PP_SCREENSHOT_DIR || 'artifacts/playwright';

test('selected route preview cursor animates from A to B', async ({ page }) => {
    test.setTimeout(120000);
    await page.setViewportSize({ width: 1920, height: 1080 });

    await page.goto(`${baseURL}/map/`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#map', { timeout: 30000 });
    await page.waitForSelector('#searchButton', { timeout: 30000 });

    await page.evaluate(() => {
        const startPoint = document.getElementById('startPoint');
        const endPoint = document.getElementById('endPoint');
        const transportMode = document.getElementById('transportMode');
        const patientCondition = document.getElementById('patientCondition');

        startPoint.value = 'Unimore campus, Reggio Emilia';
        startPoint.dataset.lat = '44.70251104660425';
        startPoint.dataset.lon = '10.628399396874087';
        endPoint.value = 'Reggio Emilia center';
        endPoint.dataset.lat = '44.6974948';
        endPoint.dataset.lon = '10.6426597';

        if (transportMode) {
            transportMode.value = 'walking';
            transportMode.dispatchEvent(new Event('change', { bubbles: true }));
        }

        if (patientCondition) {
            patientCondition.value = 'none';
            patientCondition.dispatchEvent(new Event('change', { bubbles: true }));
        }

        [startPoint, endPoint].forEach(input => {
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        });
    });

    await page.click('#searchButton');
    await page.waitForSelector('.route-selector .route-preview-button:not([disabled])', { timeout: 90000 });

    const previewButton = page.locator('.route-preview-button');
    await expect(previewButton).toBeEnabled();

    await previewButton.click();
    await page.waitForSelector('.route-preview-cursor', { timeout: 10000 });
    await page.screenshot({ path: `${screenshotDir}/cursor-preview-start.png` });

    await page.waitForTimeout(3250);
    await page.screenshot({ path: `${screenshotDir}/cursor-preview-mid.png` });

    await page.waitForTimeout(4200);
    await expect(previewButton).toHaveAttribute('data-preview-state', 'complete', { timeout: 10000 });
    await page.screenshot({ path: `${screenshotDir}/cursor-preview-end.png` });

    await previewButton.click();
    await expect(previewButton).toHaveAttribute('data-preview-state', 'running', { timeout: 5000 });

    const routeRadios = page.locator('.route-selector input[name="route-selection"]');
    if (await routeRadios.count() > 1) {
        await routeRadios.nth(1).check({ force: true });
        await expect(page.locator('.route-preview-cursor')).toHaveCount(0, { timeout: 5000 });
    }
});
