'use strict';
const {openStore}=require('./store.cjs');
const {pathToFileURL}=require('node:url');
const path=require('node:path');
const MAX=20*1024*1024;
async function createApi({root,origin}){
 const url=new URL(origin);if((url.protocol!=='https:'&&!(url.protocol==='http:'&&['127.0.0.1','localhost'].includes(url.hostname)))||url.origin!==origin)throw Error('TASKTIMER_PUBLIC_ORIGIN must be an HTTPS origin without trailing slash');
 const {validateDocument,canonical,mergeDocuments}=await import(pathToFileURL(path.resolve(__dirname,'../public/sync-protocol.mjs')));
 const store=openStore(root);let uploads=0;
 return {close:()=>store.close(),async handle(req,res){
 let uploading=false;
 const reply=(status,body='',extra={})=>{if(status>=400)req.resume();res.writeHead(status,{...(status>=400?{connection:'close'}:{}),'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff',...extra});res.end(req.method==='HEAD'?undefined:body);};
 try{
 if(req.headers.origin&&req.headers.origin!==origin)return reply(403,'{"error":"Origin denied"}');
 if(req.headers['sec-fetch-site']==='cross-site')return reply(403,'{"error":"Cross-site request denied"}');
 const token=/^Bearer ([A-Za-z0-9_-]{43})$/.exec(req.headers.authorization||'')?.[1];
 if(!store.authorized(token))return reply(401,'{"error":"Invalid or revoked device key"}');
 if(req.url!=='/api/sync')return reply(404);
 if(req.method==='GET'){const state=store.read();return state?reply(200,state.body,{etag:state.etag}):reply(404);}
 if(req.method!=='PUT')return reply(405,'',{'allow':'GET, PUT'});
 if(uploads>=4)return reply(429,'{"error":"Too many uploads"}',{'retry-after':'30'});
 uploading=true;uploads++;
 if(!/^application\/json(?:\s*;|$)/i.test(req.headers['content-type']||''))return reply(415);
 const create=req.headers['if-none-match']==='*',etag=req.headers['if-match'];
 if((req.headers['if-none-match']!==undefined&&!create)||(create&&etag)||(!create&&!/^"[a-f0-9]{64}"$/.test(etag||'')))return reply(428,'{"error":"Conditional write required"}');
 if(Number(req.headers['content-length'])>MAX)return reply(413);
 const chunks=[];let size=0;for await(const chunk of req){size+=chunk.length;if(size>MAX){reply(413);return;}chunks.push(chunk);}
 let body,doc;try{doc=validateDocument(JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks))));body=canonical(doc);}catch{return reply(400,'{"error":"Invalid synchronization document"}');}
 // Never accept removal or alteration of acknowledged causal history.
 if(!store.authorized(token))return reply(401);
 const prior=store.read();
 if(create?!!prior:(!prior||prior.etag!==etag))return reply(412);
 if(prior){try{if(canonical(mergeDocuments(JSON.parse(prior.body),doc))!==canonical(mergeDocuments(doc,doc)))return reply(409,'{"error":"Document must retain acknowledged history"}');}catch{return reply(409,'{"error":"Incompatible causal history"}');}}
 const next=store.write(body,{etag,create});return next?reply(204,'',{etag:next}):reply(412,'{"error":"Version changed; reread and merge"}');
 }catch(error){
 // Never log body, authorization or database contents.
 console.error('Synchronization request failed:',error.code||error.name||'Error');
 return reply(503,'{"error":"Storage unavailable; local data retained"}');
 }finally{if(uploading)uploads--;}
 }};
}
module.exports={createApi};
