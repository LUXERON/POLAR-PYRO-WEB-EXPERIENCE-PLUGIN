import { chromium } from "playwright";

const url=process.argv[2];
if(!url) throw new Error("review URL required");
const browser=await chromium.launch({headless:true});
const violations=[];
try{
  const page=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:"reduce"});
  page.on("console",msg=>{if(msg.type()==="error") violations.push(`console: ${msg.text()}`)});
  page.on("pageerror",error=>violations.push(`pageerror: ${error.message}`));
  await page.goto(url,{waitUntil:"networkidle"});
  if(await page.locator("h1").count()!==1) violations.push("exactly one application h1 required");
  if(await page.getByRole("navigation",{name:"Primary navigation"}).count()!==1) violations.push("primary navigation missing");
  for(const state of ["loading","empty","ready","error","recovering","forbidden"]){if(await page.locator(`[data-state="${state}"]`).count()<1) violations.push(`state missing: ${state}`)}
  await page.evaluate(()=>{window.__luxeronCommand=null;window.addEventListener("luxeron:command",event=>{window.__luxeronCommand=event.detail.id},{once:true})});
  const action=page.locator("[data-command]").first();
  if(await action.count()){await action.click();if(!await page.evaluate(()=>window.__luxeronCommand)) violations.push("command did not emit typed event")}
  await page.setViewportSize({width:390,height:844}); await page.reload({waitUntil:"networkidle"});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth)) violations.push("mobile horizontal overflow");
  await page.screenshot({path:process.argv[3]??"browser-evidence.png",fullPage:true});
}finally{await browser.close()}
console.log(JSON.stringify({verdict:violations.length?"FAIL":"PASS",violations}));
if(violations.length) process.exit(1);
