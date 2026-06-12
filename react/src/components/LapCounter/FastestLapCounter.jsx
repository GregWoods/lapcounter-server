import './FastestLapCounter.css';
import './DriverColors.css';
import { useState, useEffect } from 'react';

const BAR_HEIGHT_REM = 3.5;

function formatTime(seconds) {
    return seconds != null ? seconds.toFixed(3) : '–';
}

function formatCountdown(secs) {
    if (secs == null) return '–';
    const s = Math.max(0, secs);
    const m = Math.floor(s / 60);
    const rem = s % 60;
    const secStr = rem.toFixed(2).padStart(5, '0');
    return `${m}:${secStr}`;
}

const FastestLapCounter = ({ raceState, pendingRace }) => {
    const [timeRemaining, setTimeRemaining] = useState(null);

    // Source of truth for session drivers: live race_state when available,
    // falling back to the pending race payload before the first MQTT message.
    const sessionDrivers = raceState?.session_drivers ?? pendingRace?.session_drivers ?? [];

    // Before any races, sort alphabetically. Once lap times exist, sort by
    // session fastest lap ascending (nulls at the end).
    const anyHasTime = sessionDrivers.some(d => d.session_fastest_lap != null);
    const sortedDrivers = [...sessionDrivers].sort((a, b) => {
        if (!anyHasTime) return a.driver_name.localeCompare(b.driver_name);
        if (a.session_fastest_lap == null && b.session_fastest_lap == null)
            return a.driver_name.localeCompare(b.driver_name);
        if (a.session_fastest_lap == null) return 1;
        if (b.session_fastest_lap == null) return -1;
        return a.session_fastest_lap - b.session_fastest_lap;
    });

    const fastestSessionLap = sessionDrivers
        .map(d => d.session_fastest_lap)
        .filter(t => t != null)
        .reduce((best, t) => (best == null || t < best ? t : best), null);

    const fastestRaceLap = raceState?.race_fastest_lap ?? null;

    useEffect(() => {
        const endTime = raceState?.race_end_time;
        if (!endTime || raceState?.state !== 'Running') {
            setTimeRemaining(null);
            return;
        }
        const tick = () => setTimeRemaining(Math.max(0, endTime - Date.now() / 1000));
        tick();
        const id = setInterval(tick, 10);
        return () => clearInterval(id);
    }, [raceState?.race_end_time, raceState?.state]);

    const containerHeightRem = sortedDrivers.length * BAR_HEIGHT_REM;

    return (
        <div id="flc-layout">
            <div id="flc-main">
                <div
                    id="flc-driver-list"
                    style={{ height: `${containerHeightRem}rem` }}
                >
                    {sortedDrivers.map((driver, index) => {
                        const colorClass = driver.in_current_race
                            ? `driver${driver.lane}`
                            : 'flc-inactive';
                        const laps = driver.current_race_laps ?? [];
                        return (
                            <div
                                key={driver.driver_id}
                                className={`flc-driver-bar ${colorClass}`}
                                style={{ top: `${index * BAR_HEIGHT_REM}rem` }}
                            >
                                <div className="flc-pos">
                                    {anyHasTime && driver.session_fastest_lap != null
                                        ? index + 1
                                        : '–'}
                                </div>
                                <div className={`flc-name${driver.in_current_race ? ' emphasized' : ''}`}>
                                    {driver.driver_name}
                                </div>
                                <div className="flc-session-best">
                                    {formatTime(driver.session_fastest_lap)}
                                </div>
                                <div className="flc-lap-times">
                                    {laps.map((t, i) => (
                                        <span key={i} className="flc-lap">{t.toFixed(3)}</span>
                                    ))}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            <div id="flc-sidebar">
                <div className="flc-stat-card">
                    <div className="flc-stat-label">Fastest<br />Session Lap</div>
                    <div className="flc-stat-value flc-purple">
                        {formatTime(fastestSessionLap)}
                    </div>
                </div>
                <div className="flc-stat-card">
                    <div className="flc-stat-label">Fastest<br />Race Lap</div>
                    <div className="flc-stat-value flc-green">
                        {formatTime(fastestRaceLap)}
                    </div>
                </div>
                <div className="flc-stat-card">
                    <div className="flc-stat-label">Race Time<br />Remaining</div>
                    <div className="flc-stat-value flc-countdown">
                        {formatCountdown(timeRemaining)}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default FastestLapCounter;
