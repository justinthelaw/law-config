/**
 * Reproducible local HTML rendering and interaction QA.
 * Prerequisite: an already installed Playwright package and usable browser.
 * Run: node render-guide.mjs
 * Optional: BROWSER_ENGINE=firefox BROWSER_EXECUTABLE=/path/to/firefox node render-guide.mjs
 * No network requests, package installation, or sandbox bypass flags are used.
 */
import fs from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
const require=createRequire(import.meta.url);
const {chromium,firefox}=require('playwright');
const engine=process.env.BROWSER_ENGINE||'chromium';
if(!['chromium','firefox'].includes(engine))throw new Error('BROWSER_ENGINE must be chromium or firefox');
const base=path.dirname(fileURLToPath(import.meta.url));
const qa=await fs.mkdtemp(path.join(tmpdir(),'develop-browser-qa-'));
const evidencePath=name=>path.resolve(qa,name);
const sha256=data=>createHash('sha256').update(data).digest('hex');
const sourceFiles=['develop-overview.html','develop-route-explorer.html','render-guide.mjs'];
const sourceHashes=Object.fromEntries(await Promise.all(sourceFiles.map(async name=>[name,sha256(await fs.readFile(path.join(base,name)))])));
const launch={headless:true};
if(engine==='chromium')launch.chromiumSandbox=true;
const sandboxVariables=['MOZ_DISABLE_CONTENT_SANDBOX','MOZ_DISABLE_GMP_SANDBOX','MOZ_DISABLE_RDD_SANDBOX','MOZ_DISABLE_GPU_SANDBOX','MOZ_DISABLE_SOCKET_PROCESS_SANDBOX'];
if(engine==='firefox')for(const key of sandboxVariables){
 if(process.env[key]&&process.env[key]!=='0')throw new Error(`Refusing sandbox-disabling environment variable ${key}`);
}
if(process.env.BROWSER_EXECUTABLE)launch.executablePath=process.env.BROWSER_EXECUTABLE;
let browser;
const report={browserName:engine,timestamp:new Date().toISOString(),pass:false,sourceHashes,networkRequests:[],errors:[],checks:[],screenshots:[]};
try{
 browser=await ({chromium,firefox}[engine]).launch(launch);
 report.browser=browser.version();
 const page=await browser.newPage({viewport:{width:1000,height:1800},deviceScaleFactor:2});
 page.on('pageerror',e=>report.errors.push(e.message));
 await page.route('**/*',route=>{const url=route.request().url();if(url.startsWith('file:')||url.startsWith('data:'))return route.continue();report.networkRequests.push(url);return route.abort();});
 await page.goto(pathToFileURL(path.join(base,'develop-overview.html')).href);
 await page.evaluate(()=>document.fonts.ready);
 await page.locator('.sheet').screenshot({path:path.join(qa,'develop-overview.png')});
 report.screenshots.push(evidencePath('develop-overview.png'));
 const overviewChecks=await page.evaluate(()=>{
  const sheet=document.querySelector('.sheet'),boundary=sheet.getBoundingClientRect();
  const within=(r,b)=>r.left>=b.left-1&&r.right<=b.right+1&&r.top>=b.top-1&&r.bottom<=b.bottom+1;
  const elements=[...sheet.querySelectorAll('.card,.call,.review-source,.route-pills,.shared,.loop,.legend,.foot')].map(el=>{
   const r=el.getBoundingClientRect();
   return{target:el.className,withinSheet:within(r,boundary),contentFits:el.scrollHeight<=el.clientHeight+2&&el.scrollWidth<=el.clientWidth+2};
  });
  const textFailures=[],walker=document.createTreeWalker(sheet,NodeFilter.SHOW_TEXT);
  while(walker.nextNode()){
   const node=walker.currentNode;if(!node.textContent.trim())continue;
   const range=document.createRange();range.selectNodeContents(node);
   const owner=node.parentElement.closest('.card,.call,.review-source,.route-pills,.shared,.loop,.legend,.foot')||sheet;
   for(const r of range.getClientRects())if(!within(r,boundary)||!within(r,owner.getBoundingClientRect()))textFailures.push(node.textContent);
  }
  return{elements,textFailures,width:boundary.width,height:boundary.height,minBodyFont:Math.min(...[...sheet.querySelectorAll('p,.call,.route-pills span')].map(el=>parseFloat(getComputedStyle(el).fontSize)))};
 });
 report.checks.push({test:'overview element and text bounds',pass:overviewChecks.elements.every(c=>c.withinSheet&&c.contentFits)&&overviewChecks.textFailures.length===0,results:overviewChecks});
 report.checks.push({test:'overview README typography floor',pass:overviewChecks.width===1000&&overviewChecks.minBodyFont>=20,readmeWidth:860,minBodyDisplayPx:overviewChecks.minBodyFont*860/overviewChecks.width});
 const png=await fs.readFile(path.join(qa,'develop-overview.png'));
 report.generatedImage={sha256:sha256(png),width:png.readUInt32BE(16),height:png.readUInt32BE(20)};
 // Render the generated PNG as an actual <img>, not a scaled copy of its source DOM.
 const readmeFile=path.join(qa,'readme-preview.html');
 await fs.writeFile(readmeFile,`<!doctype html><meta charset="utf-8"><title>README image QA</title><style>body{margin:32px;background:#fff;font:16px system-ui}p{margin:0 0 16px}img{display:block;width:860px;height:auto}</style><p>README image · 860 CSS px · generated PNG</p><img src="${pathToFileURL(path.join(qa,'develop-overview.png')).href}" alt="Develop skill call map">`);
 const readme=await browser.newPage({viewport:{width:924,height:1000},deviceScaleFactor:1});
 readme.on('pageerror',e=>report.errors.push(e.message));
 await readme.route('**/*',route=>{const url=route.request().url();if(url.startsWith('file:')||url.startsWith('data:'))return route.continue();report.networkRequests.push(url);return route.abort();});
 await readme.goto(pathToFileURL(readmeFile).href);
 await readme.locator('img').evaluate(img=>img.decode());
 const imageCheck=await readme.locator('img').evaluate(img=>({src:img.currentSrc,complete:img.complete,naturalWidth:img.naturalWidth,naturalHeight:img.naturalHeight,displayWidth:img.getBoundingClientRect().width,displayHeight:img.getBoundingClientRect().height,dpr:devicePixelRatio}));
 await readme.locator('img').screenshot({path:path.join(qa,'overview-readme-860.png')});
 await readme.screenshot({path:path.join(qa,'readme-display.png'),fullPage:true});
 report.screenshots.push(evidencePath('overview-readme-860.png'),evidencePath('readme-display.png'));
 // Full image plus contiguous display-size slices support readable pixel inspection.
 await readme.setViewportSize({width:924,height:Math.ceil(imageCheck.displayHeight)+100});
 const imageBox=await readme.locator('img').boundingBox();
 for(let y=0,index=1;y<imageBox.height;y+=900,index++){
  const name=`readme-860-part-${index}.png`;
  await readme.screenshot({path:path.join(qa,name),clip:{x:imageBox.x,y:imageBox.y+y,width:imageBox.width,height:Math.min(900,imageBox.height-y)}});
  report.screenshots.push(evidencePath(name));
 }
 report.checks.push({test:'actual PNG at README display width',pass:imageCheck.complete&&imageCheck.naturalWidth===report.generatedImage.width&&imageCheck.naturalHeight===report.generatedImage.height&&imageCheck.displayWidth===860&&imageCheck.dpr===1,results:imageCheck});
 await readme.close();
 for(const viewport of [{name:'desktop',width:1440,height:1000},{name:'mobile',width:390,height:844}]){
  await page.setViewportSize({width:viewport.width,height:viewport.height});
  await page.goto(pathToFileURL(path.join(base,'develop-route-explorer.html')).href);
  await page.evaluate(()=>document.fonts.ready);
  await page.screenshot({path:path.join(qa,`explorer-${viewport.name}.png`),fullPage:true});
  report.screenshots.push(evidencePath(`explorer-${viewport.name}.png`));
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
  await page.locator('[data-route="refactor"]').click();
  await page.locator('#explore').screenshot({path:path.join(qa,`explorer-${viewport.name}-refactor.png`)});
  report.screenshots.push(evidencePath(`explorer-${viewport.name}-refactor.png`));
  const explorerBounds=await page.evaluate(()=>[...document.querySelectorAll('.node,.choice,.path-card,.skill-card,.loop-step')].flatMap(el=>{
   // Phase connectors intentionally extend beyond their cards; test the actual text.
   const bounds=el.getBoundingClientRect(),walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT),failures=[];
   while(walker.nextNode()){
    const node=walker.currentNode;if(!node.textContent.trim())continue;
    const range=document.createRange();range.selectNodeContents(node);
    if([...range.getClientRects()].some(r=>r.left<bounds.left-1||r.right>bounds.right+1||r.top<bounds.top-1||r.bottom>bounds.bottom+1))failures.push({target:el.id||el.className,text:node.textContent.trim()});
   }
   return failures;
  }));
  report.checks.push({test:`${viewport.name}: explorer content bounds`,pass:explorerBounds.length===0,failures:explorerBounds});
  await page.locator('[data-route="deep"]').click();
  await page.locator('#explore').screenshot({path:path.join(qa,`explorer-${viewport.name}-explicit-route.png`)});
  report.screenshots.push(evidencePath(`explorer-${viewport.name}-explicit-route.png`));
 }
 await page.setViewportSize({width:1440,height:1000});
 await page.goto(pathToFileURL(path.join(base,'develop-route-explorer.html')).href);
 await page.keyboard.press('Tab');
 report.checks.push({test:'keyboard skip link',pass:await page.locator('.skip').evaluate(el=>el===document.activeElement)});
 report.pass=report.errors.length===0&&report.networkRequests.length===0&&report.checks.every(c=>c.pass!==false);
 const finalHashes=Object.fromEntries(await Promise.all(sourceFiles.map(async name=>[name,sha256(await fs.readFile(path.join(base,name)))])));
 report.checks.push({test:'source provenance unchanged during rendering',pass:JSON.stringify(sourceHashes)===JSON.stringify(finalHashes)});
 report.pass=report.pass&&report.checks.at(-1).pass;
 if(report.pass)await fs.copyFile(path.join(qa,'develop-overview.png'),path.join(base,'develop-overview.png'));
}catch(error){
 report.pass=false;
 report.errors.push(error.stack||String(error));
}finally{
 try{await browser?.close();}catch(error){
  report.pass=false;
  report.errors.push(error.stack||String(error));
 }
 report.screenshotHashes=Object.fromEntries(await Promise.all(report.screenshots.map(async file=>[path.basename(file),sha256(await fs.readFile(file))])));
 await fs.writeFile(path.join(qa,'browser-qa.json'),JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({report:evidencePath('browser-qa.json'),pass:report.pass,checks:report.checks.length,screenshots:report.screenshots,errors:report.errors},null,2));
 if(!report.pass)process.exitCode=1;
}
