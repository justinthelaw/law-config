import { pathToFileURL } from 'node:url';
const {parseSwapfileSize}=await import(pathToFileURL(process.cwd()+'/build/action/planner.js'));
if(process.env.PANEL_STAGE!=='contract'){
  if(parseSwapfileSize('2MiB')!==2097152n || parseSwapfileSize('0')!==0n)process.exit(42);
}else{
  for(const raw of ['0.0000000000000000001GiB','0.0000000000000000001MiB']){
    try{const result=parseSwapfileSize(raw);console.log(raw,result);process.exit(42)}
    catch(e){console.log(e.message);if(!e.message.includes('at least 1 MiB'))process.exit(42)}
  }
}
