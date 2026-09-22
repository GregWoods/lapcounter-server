import './FastestLapCounter.css';
import './DriverColors.css';
import { useState, useEffect, useRef } from 'react';

const BAR_HEIGHT_REM = 5.0;
const GAP_REM = 0.3;
const BREAK_GAP_REM = 2.2;  // extra space inserted where the leaderboard is non-contiguous
const MOVE_MS = 600;        // must match `transition: top` duration in CSS
const MAX_VISIBLE = 12;     // racing drivers + the rivals they're chasing

// z-index tiers (kept well below the modal overlay so start lights sit on top)
const Z_RISING = 30;   // a driver actively animating upward — paints over everyone
const Z_RACING = 10;   // in the current race — always above greyed-out idle drivers
const Z_IDLE = 1;      // not in the current race

function formatTime(seconds) {
    return seconds != null ? seconds.toFixed(3) : '–';
}

// Pad single-digit-seconds lap times with a figure space (U+2007, one digit
// wide) so badges line up with tabular figures regardless of digit count.
const FIGURE_SPACE = ' ';
function formatLap(t) {
    const s = t.toFixed(3);
    const intLen = s.indexOf('.');
    return intLen < 2 ? FIGURE_SPACE.repeat(2 - intLen) + s : s;
}

function formatCountdown(secs) {
    if (secs == null) return '–';
    const s = Math.max(0, secs);
    const m = Math.floor(s / 60);
    const rem = s % 60;
    const secStr = rem.toFixed(2).padStart(5, '0');
    return `${m}:${secStr}`;
}

/*
 * Choose which leaderboard rows to show. The sole job of collapsing is to keep the
 * currently-racing drivers on screen without scrolling; everything below the last
 * racer can be shown in full (it just overflows into a scroll nobody uses mid-race).
 *
 *  1. Always include the session leader (P1) so it stays pinned at the top, and
 *     every racing driver plus the driver immediately above them (their rival).
 *  2. Include *all* drivers below the last racer — they never push racers off-screen.
 *  3. Above the last racer, where rows must fit, close the *smallest* gaps between
 *     anchors first within MAX_VISIBLE — fully or not at all. Two idle drivers wedged
 *     between racers get pulled back in; a large gap stays collapsed into a break.
 *
 * Returns a Set of indices into the full sorted leaderboard.
 */
function computeVisibleSet(sorted, maxVisible) {
    const racing = [];
    sorted.forEach((d, i) => { if (d.in_current_race) racing.push(i); });

    // No racing drivers known (e.g. the pre-race pending payload omits
    // `in_current_race`) — there's nothing to collapse around, so show everyone.
    if (racing.length === 0) return new Set(sorted.map((_, i) => i));

    const include = new Set();
    if (sorted.length > 0) include.add(0); // pin the session leader at the top
    racing.forEach(i => { include.add(i); if (i - 1 >= 0) include.add(i - 1); });

    // Trailing drivers below the last racer are shown in full — uncapped.
    const lastRacing = racing[racing.length - 1];
    for (let i = lastRacing + 1; i < sorted.length; i++) include.add(i);

    // Only the region down to the last racer has to fit without scrolling.
    const upper = () => [...include].filter(i => i <= lastRacing).sort((a, b) => a - b);
    let spare = maxVisible - upper().length;
    if (spare > 0) {
        const inc = upper();
        const gaps = [];
        for (let k = 0; k < inc.length - 1; k++) {
            const size = inc[k + 1] - inc[k] - 1;
            if (size > 0) gaps.push({ lo: inc[k], hi: inc[k + 1], size });
        }
        gaps.sort((a, b) => a.size - b.size);
        for (const g of gaps) {
            if (g.size <= spare) {
                for (let i = g.lo + 1; i < g.hi; i++) include.add(i);
                spare -= g.size;
            }
        }
    }
    return include;
}

const FastestLapCounter = ({ raceState, pendingRace }) => {
    const [timeRemaining, setTimeRemaining] = useState(null);
    const prevSlotRef = useRef({});      // driver_id -> previous visible slot index
    const elevatedUntilRef = useRef({}); // driver_id -> timestamp the upward animation ends

    const sessionDrivers = raceState?.session_drivers ?? pendingRace?.session_drivers ?? [];

    const anyHasTime = sessionDrivers.some(d => d.session_fastest_lap != null);
    const sortedDrivers = [...sessionDrivers].sort((a, b) => {
        if (!anyHasTime) return a.driver_name.localeCompare(b.driver_name);
        if (a.session_fastest_lap == null && b.session_fastest_lap == null)
            return a.driver_name.localeCompare(b.driver_name);
        if (a.session_fastest_lap == null) return 1;
        if (b.session_fastest_lap == null) return -1;
        return a.session_fastest_lap - b.session_fastest_lap;
    });

    // Name column width: fixed across all bars so every tile is identical
    const longestNameLen = sessionDrivers.reduce((m, d) => Math.max(m, d.driver_name.length), 6);
    const nameColWidth = `${Math.max(10, longestNameLen * 1.7)}rem`;

    // Filter to the visible window, keeping each driver's true leaderboard position.
    const includeSet = computeVisibleSet(sortedDrivers, MAX_VISIBLE);
    const visible = sortedDrivers
        .map((driver, i) => ({ driver, position: i + 1 }))
        .filter((_, i) => includeSet.has(i));

    // Lay out visible rows top-to-bottom, inserting a break wherever the leaderboard
    // skips positions. Track a running y-cursor so breaks add real vertical space.
    let cursor = 0;
    const placed = [];
    const breaks = [];
    visible.forEach((entry, idx) => {
        const prev = visible[idx - 1];
        if (prev && entry.position - prev.position > 1) {
            breaks.push({ key: `brk-${prev.position}-${entry.position}`, top: cursor });
            cursor += BREAK_GAP_REM;
        }
        placed.push({ ...entry, top: cursor, slot: idx });
        cursor += BAR_HEIGHT_REM + GAP_REM;
    });
    const containerHeightRem = cursor > 0 ? cursor - GAP_REM : 0;

    // Detect upward moves vs the previous render and time-stamp them. Using a
    // timestamp (not a per-render delta) keeps a driver elevated for the whole
    // slide even if more MQTT messages arrive mid-animation — that stale delta
    // was the cause of rows "popping" behind their neighbours.
    const now = Date.now();
    placed.forEach((entry) => {
        const oldSlot = prevSlotRef.current[entry.driver.driver_id];
        if (oldSlot != null && entry.slot < oldSlot) {
            elevatedUntilRef.current[entry.driver.driver_id] = now + MOVE_MS;
        }
    });
    prevSlotRef.current = Object.fromEntries(placed.map(e => [e.driver.driver_id, e.slot]));

    const zIndexFor = (driver) => {
        const until = elevatedUntilRef.current[driver.driver_id];
        if (until && now < until) return Z_RISING;
        return driver.in_current_race ? Z_RACING : Z_IDLE;
    };

    const fastestSessionLap = sessionDrivers
        .map(d => d.session_fastest_lap)
        .filter(t => t != null)
        .reduce((best, t) => (best == null || t < best ? t : best), null);

    const fastestRaceLap = raceState?.race_fastest_lap ?? null;
    const isFinished = raceState?.state === 'Finished';

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

    return (
        <div id="flc-layout">
            <div id="flc-main" style={{ '--name-col-width': nameColWidth }}>
                <div id="flc-col-headers">
                    <div className="flc-ch-pos">Session Posn</div>
                    <div className="flc-ch-name" />
                    <div className="flc-ch-session-best">Session Fastest Lap</div>
                    <div className="flc-ch-laps">Race Lap Times</div>
                </div>
                <div
                    id="flc-driver-list"
                    style={{ height: `${containerHeightRem}rem` }}
                >
                    {breaks.map(b => (
                        <div
                            key={b.key}
                            className="flc-break"
                            style={{ top: `${b.top}rem`, height: `${BREAK_GAP_REM}rem` }}
                        >
                            ⋯
                        </div>
                    ))}
                    {placed.map(({ driver, position, top }) => {
                        const colorClass = driver.in_current_race
                            ? `driver${driver.lane}`
                            : 'flc-inactive';
                        const laps = driver.current_race_laps ?? [];
                        // Newest lap on the left — stable keys so React mounts only the new element
                        const displayLaps = [...laps].reverse();
                        return (
                            <div
                                key={driver.driver_id}
                                className={`flc-driver-bar ${colorClass}`}
                                style={{
                                    top: `${top}rem`,
                                    zIndex: zIndexFor(driver),
                                }}
                            >
                                <div className="flc-pos">
                                    {anyHasTime && driver.session_fastest_lap != null
                                        ? position
                                        : '–'}
                                </div>
                                <div className={`flc-name${driver.in_current_race ? ' emphasized' : ''}`}>
                                    {driver.driver_name}
                                </div>
                                <div className="flc-session-best">
                                    {formatTime(driver.session_fastest_lap)}
                                </div>
                                <div className="flc-lap-times">
                                    {displayLaps.map((t, i) => (
                                        <span
                                            key={laps.length - 1 - i}
                                            className={`flc-lap${i === 0 ? ' flc-lap-enter' : ''}`}
                                        >
                                            {formatLap(t)}
                                        </span>
                                    ))}
                                </div>
                                {/* Keyed by lap count: remounts on each new lap, replaying the
                                    one-shot glow that signals a fresh line crossing. */}
                                {laps.length > 0 && (
                                    <div key={`glow-${laps.length}`} className="flc-row-glow" />
                                )}
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
                    <div className="flc-stat-label">
                        {isFinished ? 'Race Finished' : <>Race Time<br />Remaining</>}
                    </div>
                    <div className={`flc-stat-value ${isFinished ? 'flc-finished' : 'flc-countdown'}`}>
                        {isFinished ? '🏁' : formatCountdown(timeRemaining)}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default FastestLapCounter;
