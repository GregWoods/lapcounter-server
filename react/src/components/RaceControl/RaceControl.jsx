import './RaceControl.css';
import { useState, useEffect, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { House, Flag, Pause, Play } from 'lucide-react';
import MqttSubscriber from '../MqttSubscriber';
import ChequeredFlagIcon from '../ChequeredFlagIcon';
import { defaultConfig } from '../../defaultConfig';

const API = import.meta.env.VITE_API_URL ?? `http://${window.location.hostname}:8000`;

const STATE_LABELS = {
    NotStarted: 'Staged',
    ArmedForStart: 'Starting…',
    Running: 'Running',
    Paused: 'Paused',
    Finished: 'Finished',
};

export default function RaceControl() {
    const [raceState, setRaceState] = useState(null);
    const [infoLoaded, setInfoLoaded] = useState(false);
    const [info, setInfo] = useState({
        meetingName: '', sessionType: null, sessionNumber: null, raceNumber: null,
        racesTotal: null, targetLaps: 20, pendingRaceId: null,
        sessionInProgress: false, nextSessionAvailable: false, activeSessionId: null,
        needsRegen: false, missingDrivers: [], sitOutCandidates: [],
    });
    const clientRef = useRef(null);

    // Pull session / next-race details the MQTT race_state doesn't carry. Pending and
    // regen-status are read-only (races are pre-populated when a session starts); a 404
    // on pending just means no session is in progress, not that one should be created.
    const loadInfo = useCallback(async () => {
        try {
            const [pendingRes, meetingRes, regenRes] = await Promise.all([
                fetch(`${API}/races/pending/`),
                fetch(`${API}/meetings/active`),
                fetch(`${API}/sessions/active/regen-status`),
            ]);
            const pending = pendingRes.ok ? await pendingRes.json() : null;
            const meeting = meetingRes.ok ? await meetingRes.json() : null;
            const regen = regenRes.ok ? await regenRes.json() : null;

            let targetLaps = 20;
            let sessionInProgress = false, nextSessionAvailable = false, activeSessionId = null;
            if (meeting?.id) {
                const sRes = await fetch(`${API}/sessions?meeting_id=${meeting.id}`);
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
                }
            }
            setInfo({
                meetingName: meeting?.name ?? '',
                sessionType: pending?.session_type ?? null,
                sessionNumber: pending?.session_number ?? null,
                raceNumber: pending?.race_number ?? null,
                racesTotal: pending?.session_races_total ?? null,
                targetLaps,
                pendingRaceId: pending?.race_id ?? null,
                sessionInProgress, nextSessionAvailable, activeSessionId,
                needsRegen: regen?.needs_regeneration ?? false,
                missingDrivers: regen?.missing_driver_names ?? [],
                sitOutCandidates: regen?.sit_out_candidates ?? [],
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

    const publish = (command, extra = {}) => {
        clientRef.current?.publish('race_control', JSON.stringify({ command, ...extra }));
    };

    const onRaceState = (rs) => {
        setRaceState(rs);
        loadInfo(); // race number / next-race may have advanced
    };

    // Live values win; fall back to the API snapshot before the first MQTT message.
    const state = raceState?.state ?? (info.pendingRaceId ? 'NotStarted' : null);
    const sessionType = raceState?.session_type ?? info.sessionType;
    const raceNumber = raceState?.race_number ?? info.raceNumber;
    const raceId = raceState?.race_id ?? info.pendingRaceId;
    const isFastestLap = sessionType === 'FastestLap';

    const live = state === 'Running' || state === 'ArmedForStart';

    const apiPost = async (path) => {
        try { await fetch(`${API}${path}`, { method: 'POST' }); } catch { /* ignore */ }
    };

    const nextRace = () => { publish('prepare', { race_id: info.pendingRaceId }); setTimeout(loadInfo, 300); };
    const startRace = () => publish('arm', { race_id: raceId, target_laps: info.targetLaps });
    const endRace = () => publish('end');
    const pauseRace = () => publish('pause');
    const resumeRace = () => publish('resume');

    // "Next Session": begin the next NotStarted session and pre-populate its queue.
    const nextSession = async () => { await apiPost('/sessions/start-next'); await loadInfo(); };

    // Regenerate the upcoming queue after the roster changed. If a race is staged but
    // not yet running, re-stage the new head so the display reflects the new lineup.
    const regenerate = async () => {
        if (!info.activeSessionId) return;
        await apiPost(`/sessions/${info.activeSessionId}/regenerate-races`);
        await loadInfo();
        if (!live) publish('prepare', {});
    };

    // Disqualify a driver who has sat out too many races: drops them from the rest of the
    // session and rebuilds the upcoming queue so remaining races refill without them.
    const disqualify = async (driverId) => {
        if (!info.activeSessionId) return;
        await apiPost(`/sessions/${info.activeSessionId}/drivers/${driverId}/disqualify`);
        await loadInfo();
        if (!live) publish('prepare', {});
    };

    return (
        <div className="rc-page">
            <MqttSubscriber
                mqttHost={defaultConfig.mqtturl}
                onRaceStateMessage={onRaceState}
                clientRef={clientRef}
            />

            <header className="rc-header">
                <Link to="/" className="rc-home"><House size={22} /></Link>
                <h1>Race Control</h1>
            </header>

            <section className="rc-info">
                <div className="rc-meeting">{info.meetingName || '—'}</div>
                <div className="rc-session">
                    {info.sessionNumber != null ? `Session ${info.sessionNumber}` : '—'}
                </div>
                <div className="rc-racenum">
                    {raceNumber ? `Race ${raceNumber}` : 'No race'}
                    {info.racesTotal ? ` of ${info.racesTotal}` : ''}
                </div>
                <div className={`rc-state rc-state--${(state ?? 'unknown').toLowerCase()}`}>
                    {STATE_LABELS[state] ?? 'Connecting…'}
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

            <section className="rc-actions">
                {live && (
                    <>
                        {!isFastestLap && (
                            <button className="rc-btn rc-btn--yellow" onClick={pauseRace}>
                                <Pause size={32} /> Yellow Flag
                            </button>
                        )}
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
                {!live && state !== 'Paused' && state !== 'NotStarted' && (
                    info.pendingRaceId ? (
                        <button className="rc-btn rc-btn--next" onClick={nextRace}>
                            <Flag size={32} /> Next Race
                        </button>
                    ) : info.nextSessionAvailable ? (
                        <button className="rc-btn rc-btn--next" onClick={nextSession}>
                            <Flag size={32} /> Next Session
                        </button>
                    ) : info.sessionInProgress ? (
                        <p className="rc-session-complete">
                            Session complete — every driver has run all their races.
                        </p>
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
