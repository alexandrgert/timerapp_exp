# Offline Russian dictation assets

Runtime: official sherpa-onnx **v1.12.32**, Apache-2.0 (see LICENSE).
Unmodified JS/WASM files extracted from:
https://github.com/k2-fsa/sherpa-onnx/releases/download/v1.12.32/sherpa-onnx-wasm-simd-1.12.32-vad-asr-en-zipformer_gigaspeech.tar.bz2
Archive SHA-256: `e68738f0c057fbeb2e95d4be7bef2eb5e9c694909c28a3931d0749b1e307359a`.
No local or CI build was performed. The upstream English `.data` is not distributed.
`getPreloadedPackage` returns an empty buffer; real Russian files are then added through
the official Emscripten `FS_createDataFile` API before recognizer creation.

Model: Zipformer RU INT8 2025-04-20, immutable upstream revision
`641de8d322c05b9087ad2927ccda4bda3cccc159`:
https://huggingface.co/csukuangfj/sherpa-onnx-zipformer-ru-int8-2025-04-20
The upstream README attributes it to https://huggingface.co/alphacep/vosk-model-ru,
whose model card declares Apache-2.0. Model files are downloaded only on explicit
user action, separately from app installation. Every file has a pinned SHA-256
and byte length in `../voice-assets.mjs`. Browser cache quota/eviction can require
reinstallation. Partial verified files survive cancellation; unverified bytes do not.

Validation: the unmodified runtime instantiated the Russian model and decoded the
upstream `test_wavs/0.wav` to `я тебя люблю` in Node's WASM runtime without network
access during inference. WAV SHA-256:
`f3ac4f6e5b818ec89bdd884f60637daa32ef0ed19a11981b7e02e3e7799dfd79`.
Chromium Worker end-to-end check was attempted but did not finish in the available
resource-constrained environment; it is not claimed passed. Real Android/iPhone
microphone, memory, CORS and service-worker offline checks remain outstanding.

The inference checker is `pwa/tests/voice-inference.check.cjs`; it needs the four
pinned model files and the upstream WAV in a directory passed as its argument.
It routes static/model responses locally, blocks model network after installation,
and exercises the real browser Worker. It does not prove production HTTPS/CORS
or service-worker offline startup. Run with an external wall-time limit.
