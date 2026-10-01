// SHA-256 values pinned to upstream v1.12.32 and the immutable Russian model revision.
export const VOICE_CACHE = 'tasktimer-voice-v1';
const modelBase = 'https://huggingface.co/csukuangfj/sherpa-onnx-zipformer-ru-int8-2025-04-20/resolve/641de8d322c05b9087ad2927ccda4bda3cccc159/';
export const VOICE_FILES = [
  {name:'sherpa-onnx-asr.js',url:'/voice-assets/sherpa-onnx-asr.js',size:49519,sha256:'c71a9817c2dd3ab69fd1967a81260428650890980d11d97cfa8e00d551e34f2b',runtime:true},
  {name:'sherpa-onnx-wasm-main-vad-asr.js',url:'/voice-assets/sherpa-onnx-wasm-main-vad-asr.js',size:95452,sha256:'c5ad51692d11c95ec5dbb70b76cb0b6aa788e13aa53111c783d20882c26255cd',runtime:true},
  {name:'sherpa-onnx-wasm-main-vad-asr.wasm',url:'/voice-assets/sherpa-onnx-wasm-main-vad-asr.wasm',size:11719405,sha256:'80099b875b0b35a7b219407e192049668d64fb771dfd0f36480d39df7d36d36c',runtime:true},
  {name:'encoder.int8.onnx',size:70876638,sha256:'eb6c12fbad810d5bc3e427802e604604c69b5943a91feebc43424dd09d9ec407'},
  {name:'decoder.onnx',size:2093080,sha256:'dcbe1ffa0211e77ca6d3a80164df13fbda3ec00e47d12b9f449f89572df12136'},
  {name:'joiner.int8.onnx',size:259417,sha256:'93f2e1d12b78d53e7802f1606488c14bb3d764b15fadf5ef6c022f6ba1fa40f7'},
  {name:'tokens.txt',size:6388,sha256:'93bbbc0bae6b78c0bbb743d4aa9fded3bb5ff3aac5f0200e3a769a5a05e0fdf6'},
].map(file => ({...file,url:file.url || modelBase+file.name}));
export const VOICE_BYTES = VOICE_FILES.reduce((sum,file)=>sum+file.size,0);
export async function verifyVoiceFile(file, bytes) {
  if(bytes.byteLength!==file.size) throw new Error(`Неполный файл модели: ${file.name}`);
  const actual=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
  if(actual!==file.sha256) throw new Error(`Неверная контрольная сумма: ${file.name}`);
  return bytes;
}
