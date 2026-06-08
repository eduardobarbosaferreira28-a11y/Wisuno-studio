const puppeteer = require('puppeteer');
const path = require('path');

(async () => {
  const browser = await puppeteer.launch();
  const page = await browser.newPage();
  await page.setViewport({ width: 2160, height: 3840 });
  
  const fileUrl = 'file://' + path.resolve(__dirname, 'outro.html').replace(/\\/g, '/');
  await page.goto(fileUrl, { waitUntil: 'networkidle0' });
  
  const outputPath = path.resolve('C:/Users/Eduardo/.gemini/antigravity/brain/097ab371-8200-48dd-a4c0-20c1a5350ffe/wisuno_outro_perfect.png');
  await page.screenshot({ path: outputPath });
  
  await browser.close();
  console.log('Saved to', outputPath);
})();
