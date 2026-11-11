// Chromium print step of the HORIZON v2 document chain.
//   cover.html / body.html  ->  out/cover.pdf / out/body.pdf   (A4, running header + footer)
// Browser: the SYSTEM Chrome/Chromium (no Playwright browser download needed).
//   CHROME_BIN overrides the path; default /usr/bin/google-chrome, then Playwright's own Chromium.
const fs = require('fs'), path = require('path');
const R = __dirname;

function loadPlaywright() {
  for (const name of ['playwright-core', 'playwright']) {
    try { return require(name); } catch (e) { /* next */ }
  }
  // global installs (NODE_PATH is not always exported)
  const roots = [process.env.NODE_PATH, '/opt/node22/lib/node_modules', '/usr/lib/node_modules',
                 '/usr/local/lib/node_modules'].filter(Boolean).flatMap(p => p.split(path.delimiter));
  for (const r of roots) for (const name of ['playwright-core', 'playwright']) {
    try { return require(path.join(r, name)); } catch (e) { /* next */ }
  }
  throw new Error('playwright / playwright-core introuvable (npm install, ou NODE_PATH)');
}
const { chromium } = loadPlaywright();

const meta = JSON.parse(fs.readFileSync(path.join(R, 'out/meta.json'), 'utf8'));
const DOCID = meta.docid, REV = meta.rev, STATUS = meta.status;
const SHORT = meta.short.replace(/'/g, '’');

// Fonts are embedded in the header/footer templates as base64 (templates cannot load files).
const f = (w, s) => 'data:font/woff2;base64,' +
  fs.readFileSync(path.join(R, `vendor/fonts/plus-jakarta-sans-latin-${w}-${s}.woff2`)).toString('base64');
const FCSS = `<style>
@font-face{font-family:PJS;src:url(${f(400, 'normal')});font-weight:400}
@font-face{font-family:PJS;src:url(${f(700, 'normal')});font-weight:700}
*{font-family:PJS,sans-serif;-webkit-print-color-adjust:exact}</style>`;

const header = `${FCSS}<div style="width:100%;padding:0 17mm;font-size:7pt;color:#0B2A3C;display:flex;justify-content:space-between;align-items:flex-end;border-bottom:.5pt solid #c9dce6;padding-bottom:3px">
<span style="font-weight:700;letter-spacing:.04em">${DOCID} &middot; ${REV}</span>
<span style="color:#6b7b85;font-size:6.4pt;max-width:110mm;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">${SHORT}</span></div>`;
const footer = `${FCSS}<div style="width:100%;padding:0 17mm;font-size:6.6pt;color:#595959;border-top:.5pt solid #dadada;padding-top:4px">
<div style="display:flex;justify-content:space-between"><span>CIRCEO SAS &middot; CONFIDENTIAL</span>
<span style="color:#8a6100;font-weight:700;letter-spacing:.05em">${STATUS}</span>
<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>
<div style="text-align:center;color:#c0392b;font-weight:700;margin-top:2px">CONFIDENTIAL &ndash; Property of CIRCEO &ndash; Under NDA</div></div>`;
const coverFooter = `${FCSS}<div style="width:100%;padding:0 17mm;font-size:6.6pt;color:#595959;text-align:center">
<div>CIRCEO SAS &middot; CONFIDENTIAL &middot; ${DOCID} ${REV}</div>
<div style="color:#c0392b;font-weight:700;margin-top:2px">CONFIDENTIAL &ndash; Property of CIRCEO &ndash; Under NDA</div></div>`;

(async () => {
  const opts = { args: ['--font-render-hinting=none', '--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] };
  const exe = process.env.CHROME_BIN || (fs.existsSync('/usr/bin/google-chrome') ? '/usr/bin/google-chrome' : null);
  if (exe) opts.executablePath = exe;
  const b = await chromium.launch(opts);
  const p = await b.newPage();
  for (const [src, dst, hdr, ftr, top] of [
      ['cover.html', 'out/cover.pdf', '<div></div>', coverFooter, '10mm'],
      ['body.html', 'out/body.pdf', header, footer, '17mm']]) {
    await p.goto('file://' + path.join(R, src), { waitUntil: 'load' });
    await p.waitForFunction('window.__mathDone===true', { timeout: 120000 });
    await p.waitForTimeout(400);
    await p.pdf({ path: path.join(R, dst), format: 'A4', printBackground: true, displayHeaderFooter: true,
      headerTemplate: hdr, footerTemplate: ftr,
      margin: { top: top, bottom: '20mm', left: '17mm', right: '17mm' } });
  }
  await b.close();
  console.log('rendered');
})();
