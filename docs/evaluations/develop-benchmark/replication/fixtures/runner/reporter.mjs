export default async function* report(events) {
  for await (const {type,data} of events) {
    if (type==="test:pass"||type==="test:fail") {
      const error=data.details?.error;
      yield JSON.stringify({event:type,name:data.name,file:data.file,nesting:data.nesting,error:error?{message:String(error.message??""),cause:String(error.cause?.message??error.cause??""),code:String(error.cause?.code??error.code??"")}:null})+"\n";
    } else if(type==="test:summary"&&data.file===undefined) {
      yield JSON.stringify({event:type,success:data.success,counts:data.counts})+"\n";
    }
  }
}
