// Récupère le son du micro bloc par bloc et le transmet à la page (AudioWorklet).
class CaptureSon extends AudioWorkletProcessor {
  process(entrees) {
    const canal = entrees[0] && entrees[0][0];
    if (canal) this.port.postMessage(canal.slice(0));
    return true;
  }
}
registerProcessor("capture-son", CaptureSon);
