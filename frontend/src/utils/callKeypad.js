// DTMF stays on the active SDK call. Never redirect the live call with REST/TwiML.
export function sendCallDigit(call, connected, digit) {
  if (!connected || !/^[0-9*#]$/.test(digit)) return false
  if (!call || typeof call.sendDigits !== 'function') return false
  if (call.status() !== 'open') return false
  call.sendDigits(digit)
  return true
}

// Handle keys only while focus is inside the keypad, not in CRM note fields.
export function keypadDigitFromEvent(event) {
  if (
    event.isComposing ||
    event.repeat ||
    event.ctrlKey ||
    event.metaKey ||
    event.altKey
  )
    return null
  return /^[0-9*#]$/.test(event.key) ? event.key : null
}

// Twilio uses 160ms tones plus 70ms gaps. Separate SDK calls must not replace
// the pending WebRTC tone buffer while a previous digit is still playing.
export function createCallDigitQueue({
  getCall,
  isConnected,
  onSent,
  onError,
}) {
  let timer = null
  let queued = []
  let activeCall = null

  function clear() {
    clearTimeout(timer)
    timer = null
    queued = []
    activeCall = null
  }

  function deliver(digit) {
    try {
      if (
        getCall() !== activeCall ||
        !sendCallDigit(activeCall, isConnected(), digit)
      ) {
        throw new Error('Call is not connected')
      }
      onSent(digit)
      timer = setTimeout(() => {
        timer = null
        if (queued.length) deliver(queued.shift())
        else activeCall = null
      }, 250)
    } catch {
      clear()
      onError()
    }
  }

  function send(digit) {
    if (!/^[0-9*#]$/.test(digit)) return
    if (timer !== null) {
      if (queued.length >= 32) {
        onError()
        return
      }
      queued.push(digit)
    } else {
      activeCall = getCall()
      deliver(digit)
    }
  }
  return { send, clear }
}
