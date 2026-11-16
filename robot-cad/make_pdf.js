// 도면 SVG 를 A3 PDF 로 인쇄한다.  실행: node robot-cad/make_pdf.js
// (Playwright 와 Chromium 이 설치된 환경에서 동작)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const out = path.join(__dirname, 'out');
  const files = fs.readdirSync(out).filter((f) => f.endsWith('_drawing.svg'));
  const browser = await chromium.launch();
  const page = await browser.newPage();
  for (const f of files) {
    const svg = fs.readFileSync(path.join(out, f), 'utf8');
    await page.setContent(`<html><body style="margin:0">${svg}</body></html>`);
    await page.pdf({ path: path.join(out, f.replace('.svg', '.pdf')), width: '420mm', height: '297mm', printBackground: true, pageRanges: '1' });
    console.log('PDF:', f.replace('.svg', '.pdf'));
  }
  await browser.close();
})();
