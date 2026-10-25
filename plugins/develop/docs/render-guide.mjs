/**
 * Reproducible local overview rendering and responsive layout QA.
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
const sourceFiles=['develop-overview.html','develop-route-explorer.html','render-guide.mjs','assets/superpowers-logo.png','assets/engineering-design-concept.png','assets/interface-design-concept.png'];
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
 await page.locator('.sheet img').evaluateAll(images=>Promise.all(images.map(img=>img.decode())));
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 await page.locator('.sheet').screenshot({path:path.join(qa,'develop-overview.png')});
 report.screenshots.push(evidencePath('develop-overview.png'));
 const expectedSkills=['develop','iterate','upgrade','adversarial-loop','clean','deep-clean','kaizen','upgrade-codex'];
 const overviewChecks=await page.evaluate(()=>{
  const sheet=document.querySelector('.sheet'),boundary=sheet.getBoundingClientRect();
  const cards=[...document.querySelectorAll('.skill-card')];
  const sections=[...sheet.querySelectorAll(':scope > section')].map(el=>el.id);
  const bodyFonts=[...sheet.querySelectorAll('.skill-card p,.flow-node p,.context-guard')].map(el=>parseFloat(getComputedStyle(el).fontSize));
  return{width:boundary.width,height:boundary.height,sections,skills:cards.filter(el=>el.dataset.skill).map(el=>el.dataset.skill),minBodyFont:Math.min(...bodyFonts),logos:cards.map(el=>{const img=el.querySelector('img');return{src:img?.getAttribute('src'),loaded:img?.complete&&img.naturalWidth>0,width:img?.getBoundingClientRect().width};})};
 });
 report.checks.push({test:'one workflow and one skill directory',pass:overviewChecks.sections.length===2&&overviewChecks.sections.includes('workflow')&&overviewChecks.sections.includes('skills'),results:overviewChecks});
 report.checks.push({test:'eight unique skill descriptions and existing logos',pass:JSON.stringify([...overviewChecks.skills].sort())===JSON.stringify([...expectedSkills].sort())&&overviewChecks.logos.every(logo=>logo.loaded&&logo.width>=48)&&new Set(overviewChecks.logos.map(logo=>logo.src)).size===10&&await page.locator('.sheet img').count()===11});
 report.checks.push({test:'compact overview with legible README typography',pass:overviewChecks.width===1000&&overviewChecks.height<=2200&&overviewChecks.minBodyFont>=20,readmeWidth:860,minBodyDisplayPx:overviewChecks.minBodyFont*860/overviewChecks.width});
 const additions=await page.evaluate(()=>{
  const ids=['engineering-design','interface-design'];
  return {order:[...document.querySelectorAll('.skill-card')].map(el=>el.dataset.skill||el.dataset.design),detached:document.querySelectorAll('.design-proposals').length,items:ids.map(id=>{
   const node=document.getElementById('node-'+id),card=document.querySelector('.skill-grid [data-design="'+id+'"]'),edge=document.querySelector('[data-design-link="'+id+'"]');
   return {id,node:!!node?.closest('.branches'),mandatory:node?.textContent.includes('Planning gate · must fire'),links:card?.querySelectorAll('a').length,twoWay:!!edge?.hasAttribute('marker-start')&&!!edge?.hasAttribute('marker-end'),d:edge?.getAttribute('d')};
  })};
 });
 report.checks.push({test:'design nodes connected to Iterate and cards integrated after Iterate',pass:additions.detached===0&&additions.order.length===10&&additions.order.slice(1,4).join(',')==='iterate,engineering-design,interface-design'&&additions.items.every(c=>c.node&&c.mandatory&&c.links===0&&c.twoWay),results:additions});
 const decision=await page.locator('.planning-decision').textContent();
 const routes=await page.locator('.review-routes').textContent();
 report.checks.push({test:'compact planning decision with three explicit review routes',pass:decision.includes('Required for applicable work')&&await page.locator('[data-design-link$="-review"]').count()===2&&['Default','Human input + review','Await response','Explicit delegation','Adversarial loop','Record assumptions + open decisions','Explicit user waiver','Within existing authority'].every(text=>routes.includes(text))&&await page.locator('.review-route').count()===3&&await page.locator('.planning-policy').count()===0&&(await page.locator('.review-return').textContent()).includes('silence is not approval')});
 const guard=await page.locator('.context-guard').evaluate(el=>({count:document.querySelectorAll('.context-guard').length,href:el.querySelector('a').href,height:el.getBoundingClientRect().height}));
 const guardTarget=fileURLToPath(guard.href);
 report.checks.push({test:'one compact shared context guard annotation',pass:guard.count===1&&guard.height<=70&&guardTarget===path.join(base,'context-guard.md')&&(await fs.readFile(guardTarget,'utf8')).includes('PreToolUse'),results:guard});
 const external=await page.locator('[data-external=superpowers]').evaluate(el=>({count:document.querySelectorAll('[data-external=superpowers]').length,href:el.querySelector('a').href,loaded:el.querySelector('img').complete&&el.querySelector('img').naturalWidth>0}));
 report.checks.push({test:'one optional Superpowers box with official source link and logo',pass:external.count===1&&external.loaded&&external.href==='https://github.com/openai/plugins/tree/main/plugins/superpowers',results:external});
 const links=await page.locator('.skill-card a').evaluateAll(anchors=>anchors.map(a=>({href:a.href,label:a.textContent.trim()})));
 for(const link of links){
  const target=fileURLToPath(link.href);
  const content=await fs.readFile(target,'utf8');
  report.checks.push({test:`skill link: ${link.label}`,pass:content.startsWith('---')&&target.endsWith('/SKILL.md'),target});
 }
 const png=await fs.readFile(path.join(qa,'develop-overview.png'));
 report.generatedImage={sha256:sha256(png),width:png.readUInt32BE(16),height:png.readUInt32BE(20)};
 // Render the generated PNG as an actual <img>, not a scaled copy of its source DOM.
 const readmeFile=path.join(qa,'readme-preview.html');
 await fs.writeFile(readmeFile,`<!doctype html><meta charset="utf-8"><title>README image QA</title><style>body{margin:32px;background:#fff;font:16px system-ui}p{margin:0 0 16px}img{display:block;width:860px;height:auto}</style><p>README image · 860 CSS px · generated PNG</p><img src="${pathToFileURL(path.join(qa,'develop-overview.png')).href}" alt="Develop workflow and skill directory">`);
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
 for(const viewport of [{name:'desktop',width:1440,height:1000},{name:'mobile',width:390,height:844},{name:'narrow-620',width:620,height:844},{name:'narrow-621',width:621,height:844},{name:'tablet-760',width:760,height:844},{name:'tablet-860',width:860,height:844},{name:'mobile-breakpoint',width:920,height:844},{name:'desktop-breakpoint',width:921,height:844},{name:'short',width:924,height:560}]){
  await page.setViewportSize({width:viewport.width,height:viewport.height});
  await page.goto(pathToFileURL(path.join(base,'develop-overview.html')).href);
  await page.evaluate(()=>document.fonts.ready);
  await page.locator('.sheet img').evaluateAll(images=>Promise.all(images.map(img=>img.decode())));
  // Allow layout-driven connectors to settle across two animation frames.
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  const layout=await page.evaluate(()=>{
   const elements=[...document.querySelectorAll('.flow-node,.skill-card,.context-guard,.review-label')];
   const failures=[];
   for(const el of elements){
    const bounds=el.getBoundingClientRect(),walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);
    while(walker.nextNode()){
     const node=walker.currentNode;if(!node.textContent.trim())continue;
     const range=document.createRange();range.selectNodeContents(node);
     for(const r of range.getClientRects())if(r.left<bounds.left-1||r.right>bounds.right+1||r.top<bounds.top-1||r.bottom>bounds.bottom+1)failures.push({target:el.id||el.className,text:node.textContent.trim()});
    }
   }
   const boxes=[...document.querySelectorAll('.flow-node')].map(el=>({id:el.id||el.className,rect:el.getBoundingClientRect()}));
   const distance=(p,r)=>Math.hypot(Math.max(r.left-p.x,0,p.x-r.right),Math.max(r.top-p.y,0,p.y-r.bottom));
   const clearance=[];
   for(const path of document.querySelectorAll('.edge')){
    const length=path.getTotalLength(),matrix=path.getScreenCTM();
    const at=t=>path.getPointAtLength(t).matrixTransform(matrix);
    for(const t of [0,length]){
     // The marker tip extends one CSS pixel beyond its endpoint; allow two for rasterization.
     const tipClearance=Math.min(...boxes.map(b=>distance(at(t),b.rect)))-2;
     if(tipClearance<5.5)clearance.push({kind:'arrow tip',path:path.getAttribute('d'),clearance:tipClearance});
    }
    for(let t=0;t<=length;t+=3){
     const point=at(t);
     for(const box of boxes)if(distance(point,box.rect)<5.5)clearance.push({kind:'path too close',target:box.id,path:path.getAttribute('d')});
    }
   }
   return{horizontalOverflow:document.documentElement.scrollWidth>innerWidth,failures,clearance,nodeCount:document.querySelectorAll('.flow-node').length,visibleLogos:[...document.querySelectorAll('.skill-card img')].filter(img=>img.complete&&img.naturalWidth>0).length};
  });
  report.checks.push({test:`${viewport.name}: visible content fits`,pass:!layout.horizontalOverflow&&layout.failures.length===0&&layout.clearance.length===0&&layout.visibleLogos===10&&layout.nodeCount>0,results:layout});
  const screenshot=`overview-${viewport.name}.png`;
  await page.screenshot({path:path.join(qa,screenshot),fullPage:true});
  report.screenshots.push(evidencePath(screenshot));
 }
 await page.goto(pathToFileURL(path.join(base,'develop-route-explorer.html')).href);
 await page.waitForURL(pathToFileURL(path.join(base,'develop-overview.html')).href);
 report.checks.push({test:'legacy explorer resolves to single overview',pass:await page.locator('#workflow').count()===1&&await page.locator('.skill-card').count()===10,url:page.url()});
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
