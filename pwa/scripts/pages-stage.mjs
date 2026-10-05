// Source transformation is pure and testable; filesystem staging is GitHub Actions only.
import {readFile,writeFile,mkdir,access} from 'node:fs/promises';
import {fileURLToPath,pathToFileURL} from 'node:url';
import path from 'node:path';
export const PUBLIC_FILES = [
 'index.html','app.mjs','model.mjs','desktop-domain.mjs','repository.mjs','pwa.mjs','sw.js','sync-protocol.mjs','webdav-client.mjs','sync-controller.mjs',
 'voice-ui.mjs','voice.mjs','voice-assets.mjs','voice-worker.mjs','voice-worklet.mjs','styles.css','manifest.webmanifest',
 'icons/icon.svg','icons/icon-192.png','icons/icon-512.png',
 'voice-assets/sherpa-onnx-asr.js','voice-assets/sherpa-onnx-wasm-main-vad-asr.js','voice-assets/sherpa-onnx-wasm-main-vad-asr.wasm',
 'voice-assets/LICENSE','voice-assets/PROVENANCE.md',
];
const CSP="default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; img-src 'self' blob:; connect-src 'self' https:; worker-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'none'";
export function renderAsset(relative, bytes, {basePath, revision}) {
 if(!/^\/(?:[A-Za-z0-9_-]+\/)+$/.test(basePath))throw new Error('Expected an absolute repository base path with trailing slash');
 if(!/^[a-f0-9]{40}$/.test(revision))throw new Error('Expected full Git commit SHA');
 if(!PUBLIC_FILES.includes(relative))throw new Error('Asset not allowlisted');
 const namespace='pages-'+Buffer.from(basePath).toString('hex');
 if(relative==='manifest.webmanifest') {
  const manifest=JSON.parse(bytes);manifest.id=basePath;manifest.start_url=basePath;manifest.scope=basePath;
  manifest.icons=manifest.icons.map(icon=>({...icon,src:basePath+icon.src.replace(/^\//,'')}));
  return Buffer.from(JSON.stringify(manifest,null,2)+'\n');
 }
 if(relative==='sw.js')return Buffer.from(bytes.toString().replaceAll("'/", "'"+basePath)
  .replaceAll('tasktimer-shell-','tasktimer-shell-'+namespace+'-').replaceAll('tasktimer-voice-v1','tasktimer-voice-v1-'+namespace)
  .replaceAll('__TASKTIMER_REVISION__',revision));
 if(relative==='pwa.mjs')return Buffer.from(bytes.toString().replace("register('/sw.js', {scope: '/'", `register('${basePath}sw.js', {scope: '${basePath}'`));
 if(relative==='voice-assets.mjs')return Buffer.from(bytes.toString().replaceAll("url:'/voice-assets/", "url:'"+basePath+'voice-assets/')
  .replaceAll('tasktimer-voice-v1','tasktimer-voice-v1-'+namespace));
 if(relative==='voice-worker.mjs')return Buffer.from(bytes.toString().replaceAll("'/voice-assets/", "'"+basePath+'voice-assets/'));
 if(relative==='voice.mjs')return Buffer.from(bytes.toString().replaceAll("'/voice-worklet.mjs'", `'${basePath}voice-worklet.mjs'`)
  .replaceAll("'/voice-worker.mjs'", `'${basePath}voice-worker.mjs'`).replaceAll('tasktimer-voice-install','tasktimer-voice-install-'+namespace));
 if(relative==='repository.mjs')return Buffer.from(bytes.toString().replace("name='tasktimer-pwa'", `name='tasktimer-pwa-${namespace}'`));
 if(relative!=='index.html')return bytes;
 const text=bytes.toString().replace(/\b(href|src)="\/(?!\/)([^"]*)"/g,(_,attribute,url)=>`${attribute}="${basePath}${url}"`)
   .replace('<head>',`<head>\n<meta http-equiv="Content-Security-Policy" content="${CSP}">\n<meta name="referrer" content="no-referrer">`);
 return Buffer.from(text);
}


async function stagePages() {
 if(process.env.GITHUB_ACTIONS!=='true')throw new Error('Filesystem publication staging is allowed only in GitHub Actions');
 const basePath=process.env.PWA_BASE_PATH;
 const revision=process.env.GITHUB_SHA;
 const root=fileURLToPath(new URL('../public/',import.meta.url));
 const destination=path.resolve(fileURLToPath(new URL('../../',import.meta.url)),'_site');
 try { await access(destination);throw new Error('Refusing to overwrite an existing _site directory'); }
 catch(error){if(error.code!=='ENOENT')throw error;}
 for(const relative of PUBLIC_FILES) {
  const input=await readFile(path.join(root,relative));
  const output=renderAsset(relative,input,{basePath,revision});
  const target=path.join(destination,relative);await mkdir(path.dirname(target),{recursive:true});await writeFile(target,output,{flag:'wx'});
 }
 await writeFile(path.join(destination,'.nojekyll'),'');
 console.log(`Prepared ${PUBLIC_FILES.length} public assets for ${basePath} at commit ${revision}`);
}
if(process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href===import.meta.url)await stagePages();
