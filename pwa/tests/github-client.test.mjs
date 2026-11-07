import test from 'node:test';
import assert from 'node:assert/strict';
import {createGitHubClient,githubTarget,GITHUB_DATA_PATH,MAX_GITHUB_BYTES} from '../public/github-client.mjs';
const sha='a'.repeat(40),config={repository:'sample-owner/private-data',branch:'sync/data',token:'example-test-token'};
const json=(value,status=200,headers={})=>new Response(JSON.stringify(value),{status,headers});
const file=body=>({type:'file',path:GITHUB_DATA_PATH,sha,size:new TextEncoder().encode(body).length,encoding:'base64',content:Buffer.from(body).toString('base64')});
function fixture({body='{"text":"Привет 🌍"}',metadata={private:true},branchStatus=200,fileStatus=200,putStatus=200,onPut}={}){
 const calls=[];return {calls,client:createGitHubClient({...config,fetchImpl:async(url,options)=>{calls.push({url,options});if(options.method==='PUT'){if(onPut)return onPut(url,options);return json({},putStatus);}if(url.endsWith('/private-data'))return json(metadata);if(url.includes('/branches/'))return json({},branchStatus);return fileStatus===200?json(file(body)):json({},fileStatus);}})};
}
test('target validation never accepts API URL overrides, traversal or ambiguous references',()=>{
 assert.equal(githubTarget(' sample-owner/private-data ','main').key,'github:sample-owner/private-data:main:data/state.v2.json');
 for(const repository of ['https://other.test/repo','a/b/c','a/..','a/b?token=x','a/b#fragment'])assert.throws(()=>githubTarget(repository));
 for(const branch of ['../main','a..b','a/.private','main.lock','a b','/main','a\\b'])assert.throws(()=>githubTarget(config.repository,branch));
 assert.throws(()=>createGitHubClient({...config,token:'x\ny'}));
});
test('reads UTF-8 data and SHA in same API response and writes with exact SHA and branch',async()=>{
 const {client,calls}=fixture();const remote=await client.read();assert.deepEqual(remote,{body:'{"text":"Привет 🌍"}',etag:sha});
 await client.write(remote.body,{etag:remote.etag});const put=calls.find(x=>x.options.method==='PUT'),payload=JSON.parse(put.options.body);
 assert.equal(payload.sha,sha);assert.equal(payload.branch,'sync/data');assert.equal(Buffer.from(payload.content,'base64').toString(),remote.body);
 assert.ok(calls.some(x=>x.url.includes('?ref=sync%2Fdata')));
 for(const c of calls){assert.ok(c.url.startsWith('https://api.github.com/repos/sample-owner/private-data'));assert.equal(c.options.headers.Authorization,'Bearer example-test-token');assert.equal(c.options.redirect,'error');assert.equal(c.options.credentials,'omit');assert.equal(c.options.cache,'no-store');}
});
test('only file-level 404 permits creation after private repository and branch are verified',async()=>{
 const {client,calls}=fixture({fileStatus:404});assert.equal(await client.read(),null);await client.write('{}',{create:true});assert.equal('sha'in JSON.parse(calls.find(x=>x.options.method==='PUT').options.body),false);
 for(const options of [{metadata:{private:false}},{branchStatus:404}]){const f=fixture(options);await assert.rejects(f.client.read());assert.equal(f.calls.some(x=>x.url.includes('/contents/')),false);await assert.rejects(f.client.write('{}',{create:true}));assert.equal(f.calls.some(x=>x.options.method==='PUT'),false);}
});
test('auth, rate limits, validation and ambiguous failed writes are actionable and never retried by client',async()=>{
 for(const status of [401,403,429,422,409]){
 const {client,calls}=fixture({putStatus:status});await assert.rejects(client.write('{}',{etag:sha}),e=>{assert.equal(e.status,status);assert.equal(e.code===412,status===409);assert.ok(!e.message.includes(config.token));return true;});assert.equal(calls.filter(x=>x.options.method==='PUT').length,1);
 }
 const f=fixture({onPut:()=>{throw new Error('private internal network detail');}});await assert.rejects(f.client.write('{}',{etag:sha}),/мог сохраниться/);assert.equal(f.calls.filter(x=>x.options.method==='PUT').length,1);
});
test('invalid encoding, file type, UTF-8 and oversized files never become sync bodies',async()=>{
 for(const change of [{encoding:'none'},{type:'symlink'},{sha:'bad'},{content:'!!!'},{content:Buffer.from([255]).toString('base64')},{size:MAX_GITHUB_BYTES+1}]){
 const client=createGitHubClient({...config,fetchImpl:async url=>url.endsWith('/private-data')?json({private:true}):url.includes('/branches/')?json({}):json({...file('{}'),...change})});await assert.rejects(client.read());
 }
 const f=fixture();await assert.rejects(f.client.write('x'.repeat(MAX_GITHUB_BYTES+1),{etag:sha}),/превышает/);assert.equal(f.calls.filter(x=>x.options.method==='PUT').length,0);
});
test('read-only check never uploads and privacy is checked again before write',async()=>{
 const f=fixture();assert.equal((await f.client.check()).exists,true);assert.equal(f.calls.some(x=>x.options.method==='PUT'),false);
 let visible=false;const client=createGitHubClient({...config,fetchImpl:async url=>url.endsWith('/private-data')?json({private:!visible}):url.includes('/branches/')?json({}):json(file('{}'))});await client.read();visible=true;await assert.rejects(client.write('{}',{etag:sha}),/приватный/);
});
