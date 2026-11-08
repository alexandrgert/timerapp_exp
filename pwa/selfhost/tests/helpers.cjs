const fs=require('node:fs/promises'),path=require('node:path'),http=require('node:http'),{spawn}=require('node:child_process'),{tmpdir}=require('node:os');
const {openStore}=require('../store.cjs');
const origin='https://selfhost.test';
async function running(t){
 const data=await fs.mkdtemp(path.join(tmpdir(),'tasktimer-selfhost-')),socket=path.join(data,'server.sock');
 const store=openStore(data),device=store.addDevice('Synthetic test device');store.close();
 const shim=`const http=require('node:http');const listen=http.Server.prototype.listen;http.Server.prototype.listen=function(){return listen.call(this,process.argv[1]);};require(process.argv[2]);`;
 const child=spawn(process.execPath,['-e',shim,socket,path.resolve(__dirname,'../server.cjs')],{env:{...process.env,PORT:'18081',CLOUDCLI_DATA_DIR:data,TASKTIMER_PUBLIC_ORIGIN:origin},stdio:['ignore','ignore','pipe']});let errors='';child.stderr.on('data',c=>errors+=c);
 t.after(async()=>{child.kill();await new Promise(resolve=>{if(child.exitCode!==null)return resolve();child.once('exit',resolve);});await fs.rm(data,{recursive:true,force:true});});
 let number=0;function request(resource,options={}){const n=++number;return new Promise((resolve,reject)=>{const req=http.request({agent:false,socketPath:socket,path:resource,method:options.method||'GET',headers:options.headers||{}},res=>{const chunks=[];res.on('data',c=>chunks.push(c));res.on('end',()=>resolve({status:res.statusCode,headers:res.headers,body:Buffer.concat(chunks)}));});req.on('error',e=>{e.message='Request '+n+' '+(options.method||'GET')+' '+resource+': '+e.message;reject(e);});req.end(options.body);});}
 for(let i=0;i<200;i++){try{if((await request('/health')).status===200)return {request,data,device,auth:{Authorization:'Bearer '+device.token}};}catch{}if(child.exitCode!==null)throw Error(errors);await new Promise(r=>setTimeout(r,20));}throw Error('Server startup timed out');
}
module.exports={running,origin};
