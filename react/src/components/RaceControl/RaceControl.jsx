import './RaceControl.css';
import { useState, useEffect, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useGuestBase } from '../utils/meetingPaths';
import { House, Flag, Pause, Play } from 'lucide-react';
import MqttSubscriber from '../MqttSubscriber';
import ChequeredFlagIcon from '../ChequeredFlagIcon';
import { API_URL, MQTT_URL } from '../../endpoints.js';


const STATE_LABELS = {
    NotStarted: 'Staged',
    ArmedForStart: 'Starting…',
    Running: 'Running',
    Yellow: 'Yellow Flag',
    Paused: 'Paused',
    Finished: 'Finished',
    Orphaned: 'Not tracked',
    Connecting: 'Connecting…',
};

export default function RaceControl() {
    const base = useGuestBase();
    const [raceState, setRaceState] = useState(null);
    const [infoLoaded, setInfoLoaded] = useState(false);
    const [info, setInfo] = useState({
        meetingName: '', sessionType: null, sessionNumber: null, raceNumber: null,
        racesTotal: null, targetLaps: 20, pendingRaceId: null,
        sessionInProgress: false, nextSessionAvailable: false, activeSessionId: null,
        needsRegen: false, missingDrivers: [], sitOutCandidates: [],
        runningRaceId: null, runningRaceNumber: null,
    });
    const clientRef = useRef(null);

    // Pull session / next-race details the MQTT race_state doesn't carry. Pending and
    // regen-status are read-only (races are pre-populated when a session starts); a 404
    // on pending just means no session is in progress, not that one should be created.
    const loadInfo = useCallback(async () => {
        try {
            const [pendingRes, meetingRes, regenRes, runningRes] = await Promise.all([
                fetch(`${API_URL}/races/pending/`),
                fetch(`${API_URL}/meetings/active`),
                fetch(`${API_URL}/sessions/active/regen-status`),
                fetch(`${API_URL}/races/running/`),
            ]);
            const pending = pendingRes.ok ? await pendingRes.json() : null;
            const meeting = meetingRes.ok ? await meetingRes.json() : null;
            const regen = regenRes.ok ? await regenRes.json() : null;
            const running = runningRes.ok ? await runningRes.json() : null;

            let targetLaps = 20;
            let sessionInProgress = false, nextSessionAvailable = false, activeSessionId = null;
            let sessionNumber = pending?.session_number ?? null;
            if (meeting?.id) {
                const sRes = await fetch(`${API_URL}/sessions?meeting_id=${meeting.id}`);
                if (sRes.ok) {
                    const sessions = await sRes.json();
                    const inProgress = sessions.find(s => s.state === 'InProgress');
                    const upcoming = sessions.find(s => s.state === 'NotStarted');
                    sessionInProgress = !!inProgress;
                    nextSessionAvailable = !!upcoming;
                    activeSessionId = inProgress?.id ?? null;
                    const active = inProgress ?? upcoming;
                    if (active?.end_condition === 'Laps' && active.end_condition_info) {
                        targetLaps = active.end_condition_info;
                    }
                    // /races/pending/ 404s once a session's last race finishes, so `pending`
                    // (and its session_number) is null right when a completed session's name
                    // still needs to show — fall back to the last session that actually ran
                    // (ordinal = its index, sessions come back ordered by id, same as
                    // next_race.py's session_number calculation) rather than showing "—".
                    if (sessionNumber == null) {
                        const lastRun = [...sessions].reverse().find(s => s.state !== 'NotStarted');
                        if (lastRun) sessionNumber = sessions.indexOf(lastRun) + 1;
                    }
                    // Nothing has run yet: name the session the Start Session button will begin.
                    if (sessionNumber == null && upcoming) sessionNumber = sessions.indexOf(upcoming) + 1;
                }
            }
            setInfo({
                meetingName: meeting?.name ?? '',
                sessionType: pending?.session_type ?? null,
                sessionNumber,
                raceNumber: pending?.race_number ?? null,
                racesTotal: pending?.session_races_total ?? null,
                targetLaps,
                pendingRaceId: pending?.race_id ?? null,
                sessionInProgress, nextSessionAvailable, activeSessionId,
                needsRegen: regen?.needs_regeneration ?? false,
                missingDrivers: regen?.missing_driver_names ?? [],
                sitOutCandidates: regen?.sit_out_candidates ?? [],
                runningRaceId: running?.race_id ?? null,
                runningRaceNumber: running?.race_number ?? null,
            });
        } catch {
            /* leave previous info in place */
        } finally {
            setInfoLoaded(true);
        }
    }, []);

    useEffect(() => { loadInfo(); }, [loadInfo]);

    // Ask lapdata for the current state once (race_state is not retained on the broker).
    useEffect(() => {
        const t = setTimeout(() => publish('status'), 500);
        return () => clearTimeout(t);
    }, []);

    // Until lapdata answers that status, "no race_state" means "not heard yet", not
    // "lapdata has nothing" — so a stuck-race check can't be made. If it never answers
    // (lapdata down), stop waiting so the End Race fallback for a stuck race still shows.
    const [lapdataSilent, setLapdataSilent] = useState(false);
    useEffect(() => {
        const t = setTimeout(() => setLapdataSilent(true), 5000);
        return () => clearTimeout(t);
    }, []);

    const publish = (command, extra = {}) => {
        clientRef.current?.publish('race_control', JSON.stringify({ command, ...extra }));
    };

    // Session / next-race details only move when the race changes or transitions — not
    // on every lap crossing or yellow countdown tick — so refetch (4 requests) only then.
    const lastRaceKeyRef = useRef(null);
    const onRaceState = (rs) => {
        setRaceState(rs);
        const raceKey = `${rs.race_id}:${rs.state}`;
        if (raceKey !== lastRaceKeyRef.current) {
            lastRaceKeyRef.current = raceKey;
            loadInfo();
        }
    };

    // A live race_state can legitimately lag one prepare/arm cycle behind `info` — e.g.
    // it still names the just-finished race while /races/pending/ already answers with
    // the next one — and that's fine, because `race_number` falls back through the live
    // value first below. But race numbers reset per session, so a race_state naming a
    // number higher than the current session's own total can only be a leftover from a
    // DIFFERENT, older session — "Next Session" (POST /sessions/start-next) starts a new
    // one through the API alone, with no MQTT message telling lapdata, so its last
    // broadcast can sit there naming a race from the session that just ended. Mixing
    // that stale race_number with the new session's fresh racesTotal produced the
    // impossible "Race 5 of 4" — a race number can never exceed its own session's total,
    // which is exactly the tell. Discard the whole stale message rather than one field,
    // the same way `info.pendingRaceId` is treated as "no live message yet".
    const raceStateStale = raceState && info.racesTotal != null && raceState.race_number > info.racesTotal;
    // lapdata also publishes an empty NotStarted state (race_id null) whenever no race is
    // loaded — before a session is started, or between sessions. That is "nothing staged",
    // not a race to start, so treat it like no message and let `info` decide what to offer.
    const noRaceLoaded = raceState && !raceState.race_id && raceState.state === 'NotStarted';
    const liveRaceState = raceStateStale || noRaceLoaded ? null : raceState;

    // The DB says a race is Running but lapdata isn't running it — it restarted mid-race
    // (lapdata recovers a Running race itself now, so this is the fallback for when it
    // can't, or hasn't yet). Every button below hangs off lapdata's state, so none would
    // show, and `end` over MQTT would reach a lapdata with nothing to end. Ending it
    // through the API finishes the race and runs the session auto-end. A Finished race_state
    // for that same race is not this: lapdata's finish POST is simply still in flight.
    // ⚠️ Judged on the raw message, not liveRaceState: that one is nulled for a stale or
    // empty message too, and neither means lapdata has lost anything.
    const lapdataHeard = raceState != null || lapdataSilent;
    const orphanedRaceId = info.runningRaceId != null && lapdataHeard && raceState?.race_id !== info.runningRaceId
        ? info.runningRaceId : null;
    // lapdata has a race of its own under way. Its controls must stay — a stuck race is
    // a DB record to clean up, not a reason to lose the yellow flag mid-race — and
    // nothing may stage the next race over it.
    const lapdataRaceUnderWay = ['ArmedForStart', 'Running', 'Yellow', 'Paused'].includes(raceState?.state);

    // Live values win; fall back to the API snapshot before the first MQTT message. An
    // orphaned race takes over when lapdata is idle: offering Start Race or Next Race while
    // the DB still has another race Running would stack a second one on top. With a race
    // Running in the DB and no word from lapdata yet, show nothing rather than guess.
    const state = orphanedRaceId != null && !lapdataRaceUnderWay
        ? 'Orphaned'
        : liveRaceState?.state ?? (
            info.runningRaceId != null && !lapdataHeard ? 'Connecting'
                : info.pendingRaceId ? 'NotStarted' : null);
    // ⚠️ `||`, not `??`. lapdata now publishes `race_number: null` when no race is loaded, so
    // `??` would be correct against current lapdata — but an older lapdata image publishes 0
    // (it used to default to 0), and `??` passes a 0 straight through. 0 is falsy, so the title
    // rendered "No race" even though the API had already supplied the number. Race numbers are
    // 1-based, so treating 0 as "no race" can never discard a real one, and this keeps the page
    // right against a Pi whose lapdata hasn't been redeployed yet.
    const raceNumber = state === 'Orphaned'
        ? info.runningRaceNumber
        : liveRaceState?.race_number || info.raceNumber;
    const raceId = liveRaceState?.race_id ?? info.pendingRaceId;

    const live = state === 'Running' || state === 'ArmedForStart';

    // Seconds until a yellow flag's grace period cuts power. lapdata ticks this down and
    // publishes it (like the start lights), so no viewer depends on its own clock.
    const yellowSecondsLeft = raceState?.yellow_seconds_left ?? null;

    const apiPost = async (path) => {
        try { await fetch(`${API_URL}${path}`, { method: 'POST' }); } catch { /* ignore */ }
    };

    const nextRace = () => { publish('prepare', { race_id: info.pendingRaceId }); setTimeout(loadInfo, 300); };
    const startRace = () => publish('arm', { race_id: raceId, target_laps: info.targetLaps });
    const endRace = () => publish('end');
    const yellowFlag = () => publish('yellow');
    const resumeRace = () => publish('resume');

    // Close a race lapdata has lost: finish it in the DB (which auto-ends the session if
    // that was the last race), tell other pages, then stage whatever is next — unless
    // lapdata is racing something else, which prepare would replace (lapdata refuses it
    // too, but don't rely on one guard).
    const endOrphanedRace = async () => {
        await apiPost(`/races/${orphanedRaceId}/finish`);
        clientRef.current?.publish('admin_update', JSON.stringify({ reason: 'race_finished', race_id: orphanedRaceId }));
        await loadInfo();
        if (!lapdataRaceUnderWay) publish('prepare', {});
    };

    // "Next Session": begin the next NotStarted session and pre-populate its queue.
    const nextSession = async () => { await apiPost('/sessions/start-next'); await loadInfo(); };

    // A session with every race run can still be InProgress (e.g. races_per_driver unset,
    // or the target was met some other way), so the operator ends it from here too, same
    // endpoint and admin_update ping as the Admin Sessions page.
    const endSession = async () => {
        if (!info.activeSessionId) return;
        await apiPost(`/sessions/${info.activeSessionId}/finish`);
        clientRef.current?.publish('admin_update', JSON.stringify({
            reason: 'session_finished', session_id: info.activeSessionId,
        }));
        await loadInfo();
    };

    // Regenerate the upcoming queue after the roster changed. If a race is staged but
    // not yet running, re-stage the new head so the display reflects the new lineup.
    const regenerate = async () => {
        if (!info.activeSessionId) return;
        await apiPost(`/sessions/${info.activeSessionId}/regenerate-races`);
        await loadInfo();
        if (!lapdataRaceUnderWay) publish('prepare', {});
    };

    // Disqualify a driver who has sat out too many races: drops them from the rest of the
    // session and rebuilds the upcoming queue so remaining races refill without them.
    const disqualify = async (driverId) => {
        if (!info.activeSessionId) return;
        await apiPost(`/sessions/${info.activeSessionId}/drivers/${driverId}/disqualify`);
        await loadInfo();
        if (!lapdataRaceUnderWay) publish('prepare', {});
    };

    return (
        <div className="rc-page">
            <MqttSubscriber
                mqttHost={MQTT_URL}
                onRaceStateMessage={onRaceState}
                onAdminUpdateMessage={loadInfo}
                clientRef={clientRef}
            />

            <header className="rc-header">
                <Link to={base || '/'} className="rc-home"><House size={22} /></Link>
                <h1>Race Control</h1>
            </header>

            <section className="rc-info">
                <div className="rc-meeting">{info.meetingName || '—'}</div>
                <div className="rc-session">
                    {info.sessionNumber != null ? `Session ${info.sessionNumber}` : '—'}
                </div>
                <div className="rc-racenum">
                    {/* "of N" hangs off the race number rather than standing alone, or a missing
                        number leaves the nonsense "No race of 7" — same rule as LapCounter's Header. */}
                    {raceNumber
                        ? `Race ${raceNumber}${info.racesTotal ? ` of ${info.racesTotal}` : ''}`
                        : 'No race'}
                </div>
                <div className={`rc-state rc-state--${(state ?? 'unknown').toLowerCase()}`}>
                    {/* No state with info loaded means nothing is staged, not that we're offline. */}
                    {STATE_LABELS[state] ?? (infoLoaded ? 'Not started' : 'Connecting…')}
                </div>
            </section>

            {info.needsRegen && (
                <div className="rc-regen-banner">
                    <span>
                        New driver added{info.missingDrivers.length ? ` (${info.missingDrivers.join(', ')})` : ''},
                        {' '}regenerate upcoming races?
                    </span>
                    <button className="rc-btn rc-btn--regen" onClick={regenerate}>Regenerate</button>
                </div>
            )}

            {info.sitOutCandidates.map((c) => (
                <div key={c.driver_id} className="rc-regen-banner rc-sitout-banner">
                    <span>
                        {c.driver_name} has sat out {c.sit_outs} race{c.sit_outs === 1 ? '' : 's'} —
                        {' '}disqualify from the rest of the session?
                    </span>
                    <button className="rc-btn rc-btn--regen" onClick={() => disqualify(c.driver_id)}>
                        Disqualify
                    </button>
                </div>
            ))}

            {orphanedRaceId != null && state !== 'Orphaned' && (
                <div className="rc-regen-banner">
                    <span>
                        Race {info.runningRaceNumber} is also still marked Running, but the lap
                        counter isn&apos;t tracking it.
                    </span>
                    <button className="rc-btn rc-btn--regen" onClick={endOrphanedRace}>Close it</button>
                </div>
            )}

            <section className="rc-actions">
                {state === 'Connecting' && <p className="rc-connecting">Connecting…</p>}

                {live && (
                    <>
                        <button className="rc-btn rc-btn--yellow" onClick={yellowFlag}>
                            <Pause size={32} /> Yellow Flag
                        </button>
                        <button className="rc-btn rc-btn--end" onClick={endRace}>
                            <ChequeredFlagIcon /> End Race
                        </button>
                    </>
                )}

                {state === 'Yellow' && (
                    <>
                        <div className="rc-yellow-countdown">
                            Race pauses in {yellowSecondsLeft}s
                        </div>
                        <button className="rc-btn rc-btn--start" onClick={resumeRace}>
                            <Play size={32} /> Resume Now
                        </button>
                        <button className="rc-btn rc-btn--end" onClick={endRace}>
                            <ChequeredFlagIcon /> End Race
                        </button>
                    </>
                )}

                {state === 'Paused' && (
                    <>
                        <button className="rc-btn rc-btn--start" onClick={resumeRace}>
                            <Play size={32} /> Resume Race
                        </button>
                        <button className="rc-btn rc-btn--end" onClick={endRace}>
                            <ChequeredFlagIcon /> End Race
                        </button>
                    </>
                )}

                {state === 'Orphaned' && (
                    <>
                        <p className="rc-session-complete">
                            Race {info.runningRaceNumber} is still marked Running, but the lap counter
                            has lost track of it (it was restarted mid-race).
                        </p>
                        <button className="rc-btn rc-btn--end" onClick={endOrphanedRace}>
                            <ChequeredFlagIcon /> End Race
                        </button>
                    </>
                )}

                {state === 'NotStarted' && (
                    <>
                        <button className="rc-btn rc-btn--start" onClick={startRace}>
                            <Play size={32} /> Start Race
                        </button>
                        <button className="rc-btn rc-btn--ghost" onClick={nextRace}>
                            Reload Lineup
                        </button>
                    </>
                )}

                {/* Idle (Finished / not connected): advance the race queue, start the
                    next session, or report completion. */}
                {!live && !['Yellow', 'Paused', 'NotStarted', 'Orphaned', 'Connecting'].includes(state) && (
                    info.pendingRaceId ? (
                        <button className="rc-btn rc-btn--next" onClick={nextRace}>
                            <Flag size={32} /> Next Race
                        </button>
                    ) : info.nextSessionAvailable ? (
                        <button className="rc-btn rc-btn--next" onClick={nextSession}>
                            <Flag size={32} /> Start Session
                        </button>
                    ) : info.sessionInProgress ? (
                        <>
                            <p className="rc-session-complete">
                                Session complete — every driver has run all their races.
                            </p>
                            <button className="rc-btn rc-btn--next" onClick={endSession}>
                                <Flag size={32} /> End Session
                            </button>
                        </>
                    ) : infoLoaded ? (
                        <p className="rc-session-complete">Meeting complete — no more sessions.</p>
                    ) : (
                        <p className="rc-connecting">Connecting…</p>
                    )
                )}
            </section>
        </div>
    );
}
