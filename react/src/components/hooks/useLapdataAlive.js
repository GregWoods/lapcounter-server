import { useCallback, useEffect, useRef, useState } from 'react';

// lapdata republishes race_state every 2s (HEARTBEAT_INTERVAL_S), retained, so a page
// hears it within moments of connecting and then on every beat. Silence for a few beats
// means lapdata is gone; so does its Last Will, a retained `Offline` state.
const SILENCE_MS = 7000;

// Returns [alive, noteRaceState]: call noteRaceState with every race_state message.
// Optimistic until SILENCE_MS has passed with nothing heard, so a page doesn't flash
// "offline" while its MQTT connection is still opening.
function useLapdataAlive() {
    const [alive, setAlive] = useState(true);
    const timerRef = useRef(null);

    const restartSilenceTimer = useCallback(() => {
        clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => setAlive(false), SILENCE_MS);
    }, []);

    useEffect(() => {
        restartSilenceTimer();
        return () => clearTimeout(timerRef.current);
    }, [restartSilenceTimer]);

    const noteRaceState = useCallback((raceState) => {
        if (raceState?.state === 'Offline') {
            clearTimeout(timerRef.current);
            setAlive(false);
            return;
        }
        setAlive(true);
        restartSilenceTimer();
    }, [restartSilenceTimer]);

    return [alive, noteRaceState];
}

export default useLapdataAlive;
