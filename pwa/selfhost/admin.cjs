'use strict';
// Run interactively on the server. Never commit or pipe generated device keys to CI logs.
const {openStore}=require('./store.cjs');
(async()=>{
 const store=openStore(process.env.CLOUDCLI_DATA_DIR);try{
 const [cmd,arg]=process.argv.slice(2);
 if(cmd==='add-device'){const {id,token}=store.addDevice(arg);console.log('Device ID: '+id+'\nDevice key (shown once): '+token);}
 else if(cmd==='devices')console.log(JSON.stringify(store.devices(),null,2));
 else if(cmd==='revoke'){if(!store.revoke(arg))throw Error('Active device not found');console.log('Device revoked');}
 else if(cmd==='import-v2'){
 const fs=require('node:fs/promises'),path=require('node:path'),{pathToFileURL}=require('node:url');
 if(!arg)throw Error('Provide path to exported v2 document');
 if(store.read())throw Error('Import requires an empty server database');
 const stat=await fs.stat(arg);if(stat.size>20*1024*1024)throw Error('Document exceeds 20 MiB');
 const {validateDocument,canonical}=await import(pathToFileURL(path.resolve(__dirname,'../public/sync-protocol.mjs')));
 const body=canonical(validateDocument(JSON.parse(await fs.readFile(arg,'utf8'))));
 if(!store.write(body,{create:true}))throw Error('Server was initialized concurrently; import stopped');console.log('Causal v2 history imported without changing IDs');
 }
 else if(cmd==='backup'){await store.backup(arg);console.log('Consistent SQLite backup created');}
 else throw Error('Usage: admin.cjs add-device LABEL | devices | revoke ID | import-v2 FILE | backup /absolute/new-copy.sqlite');
 }finally{store.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
