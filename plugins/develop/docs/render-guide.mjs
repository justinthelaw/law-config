/**
 * Reproducible local HTML rendering and interaction QA.
 * Prerequisite: an already installed Playwright package and usable browser.
 * Run: node render-guide.mjs
 * Optional: BROWSER_EXECUTABLE=/path/to/chromium node render-guide.mjs
 * No network requests, package installation, or sandbox bypass flags are used.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require('playwright');
const base=path.dirname(fileURLToPath(import.meta.url));
const qa=path.join(base,'qa');
await fs.mkdir(qa,{recursive:true});
const launch={headless:true,chromiumSandbox:true};
if(process.env.BROWSER_EXECUTABLE)launch.executablePath=process.env.BROWSER_EXECUTABLE;
const browser=await chromium.launch(launch);
const report={timestamp:new Date().toISOString(),browser:browser.version(),networkRequests:[],errors:[],checks:[],screenshots:[]};
try{
 const page=await browser.newPage({viewport:{width:1600,height:1190},deviceScaleFactor:2});
 page.on('pageerror',e=>report.errors.push(e.message));
 await page.route('**/*',route=>{const url=route.request().url();if(url.startsWith('file:')||url.startsWith('data:'))return route.continue();report.networkRequests.push(url);return route.abort();});
 await page.goto(pathToFileURL(path.join(base,'develop-overview.html')).href);
 await page.evaluate(()=>document.fonts.ready);
 await page.locator('.sheet').screenshot({path:path.join(base,'develop-overview.png')});
 report.screenshots.push('develop-overview.png');
 const overviewChecks=await page.evaluate(()=>{const boundary=document.querySelector('.sheet').getBoundingClientRect();return [...document.querySelectorAll('.card,.shared,.loop,.explicit-zone')].map(el=>{const r=el.getBoundingClientRect();return{target:el.className,withinSheet:r.left>=boundary.left&&r.right<=boundary.right&&r.top>=boundary.top&&r.bottom<=boundary.bottom,contentFits:el.scrollHeight<=el.clientHeight+2&&el.scrollWidth<=el.clientWidth+2}})});
 report.checks.push({test:'overview element bounds',results:overviewChecks});
 for(const viewport of [{name:'desktop',width:1440,height:1000},{name:'mobile',width:390,height:844}]){
  await page.setViewportSize({width:viewport.width,height:viewport.height});
  await page.goto(pathToFileURL(path.join(base,'develop-route-explorer.html')).href);
  await page.evaluate(()=>document.fonts.ready);
  await page.screenshot({path:path.join(qa,`explorer-${viewport.name}.png`),fullPage:true});
  report.screenshots.push(`qa/explorer-${viewport.name}.png`);
  report.checks.push({test:`${viewport.name}: horizontal overflow`,pass:await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)});
  const routeIds=await page.locator('.choice[data-route]').evaluateAll(buttons=>buttons.map(button=>button.dataset.route));
  report.checks.push({test:`${viewport.name}: route controls present and unique`,pass:routeIds.length>0&&new Set(routeIds).size===routeIds.length});
  for(const id of routeIds){
   const button=page.locator(`[data-route="${id}"]`);await button.click();
   const pressed=await button.getAttribute('aria-pressed');
   const selectedCount=await page.locator('.choice[aria-pressed="true"]').count();
   const text=await page.locator('#route-title').innerText();
   report.checks.push({test:`${viewport.name}: route ${id}`,pass:pressed==='true'&&selectedCount===1&&text.length>5,title:text});
  }
  for(const id of ['failure','success','blocked','infra']){
   const button=page.locator(`[data-loop="${id}"]`);await button.click();
   report.checks.push({test:`${viewport.name}: branch ${id}`,pass:await button.getAttribute('aria-pressed')==='true',title:await page.locator('#loop-title').innerText()});
  }
  await page.locator('[data-route="deep"]').click();
  await page.locator('#explore').screenshot({path:path.join(qa,`explorer-${viewport.name}-explicit-route.png`)});
  report.screenshots.push(`qa/explorer-${viewport.name}-explicit-route.png`);
 }
 await page.setViewportSize({width:1440,height:1000});
 await page.goto(pathToFileURL(path.join(base,'develop-route-explorer.html')).href);
 await page.keyboard.press('Tab');
 report.checks.push({test:'keyboard skip link',pass:await page.locator('.skip').evaluate(el=>el===document.activeElement)});
 report.pass=report.errors.length===0&&report.networkRequests.length===0&&report.checks.every(c=>c.pass!==false)&&overviewChecks.every(c=>c.withinSheet&&c.contentFits);
 await fs.writeFile(path.join(qa,'browser-qa.json'),JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({pass:report.pass,checks:report.checks.length,screenshots:report.screenshots,errors:report.errors},null,2));
 if(!report.pass)process.exitCode=1;
}finally{await browser.close();}
