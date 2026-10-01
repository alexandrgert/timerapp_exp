class PCMRecorder extends AudioWorkletProcessor {
  process(inputs,outputs) {
    const input=inputs[0]?.[0];
    if(input){const copy=new Float32Array(input);this.port.postMessage(copy,[copy.buffer]);}
    // Output remains zero: microphone audio is never played through speakers.
    return true;
  }
}
registerProcessor('tasktimer-pcm',PCMRecorder);
