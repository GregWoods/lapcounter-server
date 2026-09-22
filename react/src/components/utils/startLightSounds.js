// Start-light beeps, played through one shared Web Audio context.
//
// Why not `new Audio(url).play()`: a media element fetches and decodes on its first
// play, and the long beep only ever plays once per race — so it always paid that
// latency, at exactly the moment (lights out) where it shows. Here both sounds are
// fetched and decoded once, when this module loads, and play from memory.
//
// Browsers also keep audio suspended until the page has had a user gesture, and nobody
// interacts with a leaderboard display. `isSoundBlocked()` / `onSoundStateChange()` let
// the page show that, and `unlockSound()` (call it from any tap/keypress) resumes it.

const SOUND_URLS = {
    beep: 'sounds/Beep.wav',
    longBeep: 'sounds/LongBeep.wav',
};

const AudioContextClass = window.AudioContext || window.webkitAudioContext;
const ctx = AudioContextClass ? new AudioContextClass() : null;
const buffers = {};

if (ctx) {
    for (const [name, url] of Object.entries(SOUND_URLS)) {
        // Relative to the site root, whatever route the page is on.
        fetch(new URL(url, window.location.origin))
            .then(r => r.arrayBuffer())
            .then(data => ctx.decodeAudioData(data))
            .then(buffer => { buffers[name] = buffer; })
            .catch(e => console.error(`Failed to load sound ${url}:`, e));
    }
}

export const isSoundBlocked = () => !ctx || ctx.state !== 'running';

export const onSoundStateChange = (listener) => {
    if (!ctx) return () => {};
    ctx.addEventListener('statechange', listener);
    return () => ctx.removeEventListener('statechange', listener);
};

// Must be called from inside a user-gesture handler to succeed.
export const unlockSound = () => {
    if (ctx && ctx.state !== 'running') ctx.resume().catch(() => {});
};

export const playSound = (name) => {
    const buffer = buffers[name];
    // While suspended, a scheduled source would play late, on unlock — a stray beep
    // long after the light it belonged to. Better silent than wrong.
    if (!buffer || isSoundBlocked()) return;
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    source.start();
};
