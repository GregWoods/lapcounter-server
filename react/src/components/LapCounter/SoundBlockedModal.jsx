import { useEffect, useState } from 'react';
import useLocalStorageState from 'use-local-storage-state';
import ReactModal from 'react-modal';
import { isSoundBlocked, onSoundStateChange, unlockSound } from '../utils/startLightSounds.js';
import './SoundBlockedModal.css';

const DISMISS_HOURS = 24;

// Shown while the browser is holding audio back (no user gesture yet), so a silent
// start sequence isn't a surprise with no visible cause. Any tap or keypress anywhere on
// the page unlocks sound, not only one on the modal itself — a display screen may have
// no pointer to aim (no keyboard/mouse attached), and ignoring it is a legitimate choice
// in that case.
//
// `armed` (true once a race's start lights begin, i.e. it was passed the same flag that
// shows StartLights) permanently dismisses the prompt for the rest of the day, stored in
// localStorage — the operator has been told, whether or not they acted on it. Without
// this, closing on the countdown alone (armed was briefly true, then false again once
// StartLights itself closes ~1.3s after lights-out) let it silently reopen mid-race the
// moment armed went back to false, which is not "dismissed", it's just "not counting
// down right now".
const SoundBlockedModal = ({ armed }) => {
    const [blocked, setBlocked] = useState(isSoundBlocked());
    const [dismissedAt, setDismissedAt] = useLocalStorageState('soundPromptDismissedAt', {
        defaultValue: null,
    });

    useEffect(() => {
        const unsubscribe = onSoundStateChange(() => setBlocked(isSoundBlocked()));
        setBlocked(isSoundBlocked());
        return unsubscribe;
    }, []);

    useEffect(() => {
        if (armed) setDismissedAt(Date.now());
    }, [armed, setDismissedAt]);

    const dismissedRecently = dismissedAt && (Date.now() - dismissedAt) < DISMISS_HOURS * 60 * 60 * 1000;
    const showMe = blocked && !dismissedRecently && !armed;

    // Listen for as long as sound is actually blocked, not just while the prompt
    // happens to be on screen — `armed`/dismissal hide the prompt (see comment above)
    // well before a gesture has unlocked anything, and a stale listener means no tap
    // anywhere for the rest of the day can ever start the sound.
    useEffect(() => {
        if (!blocked) return;
        const events = ['pointerdown', 'keydown', 'touchend'];
        events.forEach(e => document.addEventListener(e, unlockSound, true));
        return () => events.forEach(e => document.removeEventListener(e, unlockSound, true));
    }, [blocked]);

    return (
        <ReactModal
            isOpen={showMe}
            contentLabel="Sound Blocked"
            className="soundBlockedModal"
            overlayClassName="soundBlockedModalOverlay"
            shouldCloseOnOverlayClick={false}
            shouldCloseOnEsc={false}
            ariaHideApp={false}
        >
            <div id="soundBlockedContainer" onClick={unlockSound}>
                <div id="soundBlockedIcon">🔇</div>
                <h1>Sound is off</h1>
                <p>Tap anywhere to enable start-light beeps</p>
            </div>
        </ReactModal>
    );
};

export default SoundBlockedModal;
