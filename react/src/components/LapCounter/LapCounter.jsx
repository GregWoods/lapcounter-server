import './LapCounter.css';
import useLocalStorageState from 'use-local-storage-state'
import MqttSubscriber from '../MqttSubscriber.jsx'
import DriverCard from './DriverCard.jsx';
import FastestLapCounter from './FastestLapCounter.jsx';
import Header from './Header.jsx';
import StartLights from './StartLights.jsx';
import SoundBlockedModal from './SoundBlockedModal.jsx';
import ApiUnreachableModal from './ApiUnreachableModal.jsx';
import YellowFlagRacePaused from './YellowFlagRacePaused.jsx';
import useLapdataAlive from '../hooks/useLapdataAlive.js';
import { useState, useRef, useEffect } from 'react';
import { useLoaderData } from 'react-router-dom';
import { defaultConfig, defaultRace, getInitialDrivers } from '../../defaultConfig.js';
import { API_URL, MQTT_URL, CAR_MEDIA_URL } from '../../endpoints.js';

const DEBUG = true;

const LapCounter = () => {
    const pendingRace = useLoaderData();

    const [config] = useLocalStorageState('config', {defaultValue: {...defaultConfig}});
    console.log('config', config);

    const [race, setRace] = useState(defaultRace);

    const lapsPerRace = race.RaceType?.details.laps ?? 0;

    const carMediaBase = CAR_MEDIA_URL;
    const defaultCarImg = carMediaBase + '/GT_AA_Generic.jpg';
    // Build a car image URL from a picture filename (from the pending race lineup),
    // falling back to the generic image when no car is assigned.
    const carImageUrl = (picture) => picture ? `${carMediaBase}/${picture}` : defaultCarImg;
    // Six hidden lane slots. Every card, staged lineup included, is filled from race_state:
    // lapdata publishes a NotStarted race's lineup with its positions, so React orders nothing.
    const initialDrivers = getInitialDrivers(lapsPerRace, defaultCarImg);
    const [drivers, setDrivers] = useState([...initialDrivers]);

    const [raceId, setRaceId] = useState(null);
    const raceIdRef = useRef();
    raceIdRef.current = raceId;

    const [raceNumber, setRaceNumber] = useState(pendingRace?.race_number ?? null);
    const [sessionNumber, setSessionNumber] = useState(pendingRace?.session_number ?? null);
    const [sessionRacesTotal, setSessionRacesTotal] = useState(pendingRace?.session_races_total ?? null);
    const [sessionType, setSessionType] = useState(pendingRace?.session_type ?? 'Points');
    const [fastestLapRaceState, setFastestLapRaceState] = useState(null);

    const resyncInFlightRef = useRef(false);

    // A race's identity: id, number, session labels, type.
    const applyRaceIdentity = (setup) => {
        if (setup.race_id) setRaceId(setup.race_id);
        if (setup.race_number != null) setRaceNumber(setup.race_number);
        if (setup.session_number != null) setSessionNumber(setup.session_number);
        if (setup.session_races_total != null) setSessionRacesTotal(setup.session_races_total);
        if (setup.session_type) setSessionType(setup.session_type);
    };

    // When a race_state arrives for a race other than the one we're showing, fetch that
    // race's own setup for what race_state doesn't carry: the session labels in the
    // header. Only the identity is taken: the cards, car pictures included, come from
    // race_state.
    //
    // ⚠️ The race race_state names, never /races/current/: after a session's last race the
    // DB has no current race at all, and between races its current race is the next one
    // queued while the Finished one is still on screen. Each race is fetched once, or the
    // 2s heartbeat (#76) repeats it.
    const resyncAttemptRef = useRef(null);
    const resyncCurrentRace = (incomingRaceId) => {
        if (resyncInFlightRef.current || resyncAttemptRef.current === incomingRaceId) return;
        resyncInFlightRef.current = true;
        resyncAttemptRef.current = incomingRaceId;
        fetch(`${API_URL}/races/${incomingRaceId}/setup`)
            .then(r => r.ok ? r.json() : null)
            .then(setup => { if (setup) applyRaceIdentity(setup); })
            .catch(() => {})
            .finally(() => { resyncInFlightRef.current = false; });
    };

    // Seed the header from the current race on page load; the cards wait for race_state
    // (retained, so it arrives as soon as MQTT connects).
    useEffect(() => {
        if (pendingRace) applyRaceIdentity(pendingRace);
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // No need to ask lapdata for the current state on load: race_state is retained and
    // heartbeated (#76). Silence, or its retained Offline will, means lapdata is gone.
    const [lapdataAlive, noteLapdataRaceState] = useLapdataAlive();
    // Layer 1's retained layer1_status. `online` false is its Last Will; BLE also says
    // when its powerbase link is down — the one loss where power can't be cut, so this
    // screen telling drivers to stop is all there is. A Layer 1 that says neither (GPIO)
    // is online.
    const [layer1Status, setLayer1Status] = useState(null);
    const trackOnline = layer1Status?.online !== false && layer1Status?.powerbase_connected !== false;

    const [racePhase, setRacePhase] = useState(pendingRace?.lane_assignments ? 'getready' : null);
    const [startLightsShown, setStartLightsShown] = useState(false);
    const [lightsOut, setLightsOut] = useState(false);
    const [startLights, setStartLights] = useState(0); // lit count, driven by lapdata's race_state
    const [yellowSecondsLeft, setYellowSecondsLeft] = useState(null); // grace countdown, driven by lapdata
    // Optimistic until the first race_state says otherwise — lapdata itself depends on
    // the API (pending-race queue, race lifecycle persistence), so this isn't a
    // React-only nicety; see ApiUnreachableModal.
    const [apiReachable, setApiReachable] = useState(true);
    const [previewDriverCards, setPreviewDriverCards] = useState(!!pendingRace?.lane_assignments);

    // Primary display update: map race_state from LapData onto the drivers viewmodel
    const processRaceStateMsg = (raceState) => {
        noteLapdataRaceState(raceState);
        const { state } = raceState;
        // lapdata's Last Will: says nothing about the race, so leave the last real state
        // on screen behind the offline modal rather than treating it as a new race.
        if (state === 'Offline') return;

        // Reconcile identity against the DB (authoritative for which race is
        // current). A race_state for a different race than the one we're showing is
        // either a newly-staged race or a stale lapdata broadcast — re-fetch the
        // current race to arbitrate identity/lineup fields (race number, car pictures,
        // session labels).
        //
        // ⚠️ Deliberately does NOT `return` here — the resync fetch is async and only
        // touches identity fields, so this message's own state-driven side effects
        // below (start lights, yellow overlay, driver cards) still need to run against
        // *this* raceState. Returning early once caused the ArmedForStart edge to be
        // dropped silently: the mismatch was detected exactly on that message (the
        // first one for a newly-armed race), so the light countdown never opened, and
        // by the time race_id resynced a message later the state had already moved past
        // ArmedForStart, so it never got a second chance to fire.
        if (raceState.race_id && raceState.race_id !== raceIdRef.current) {
            resyncCurrentRace(raceState.race_id);
        }

        if (raceState.race_number) {
            setRaceNumber(raceState.race_number);
        }

        // Sync session type from race_state
        if (raceState.session_type) {
            setSessionType(raceState.session_type);
        }

        // Start-light count is owned by lapdata (published as it lights each one).
        if (raceState.start_lights != null) {
            setStartLights(raceState.start_lights);
        }

        // Yellow-flag power-cut countdown, also ticked by lapdata; null outside Yellow.
        setYellowSecondsLeft(raceState.yellow_seconds_left ?? null);

        // System-wide, not race-specific — process it whatever race_id this message is
        // for. `??` (not `||`): false is a real, meaningful value here.
        if (raceState.api_reachable != null) setApiReachable(raceState.api_reachable);

        // Header phase + (Points) staged-lineup preview, driven by the live state.
        if (state === 'Finished') setRacePhase('results');
        else if (state === 'NotStarted') setRacePhase('getready');
        else setRacePhase('live');
        if (state === 'NotStarted') setPreviewDriverCards(true);
        else if (state === 'Running' || state === 'Finished') setPreviewDriverCards(false);
        // A newly staged race, or a start aborted during the lights (a lost connection):
        // nothing is lit, started or paused, so the get-ready preview replaces whatever
        // the last race left on screen.
        if (state === 'NotStarted') {
            setStartLightsShown(false);
            setLightsOut(false);
            setStartLights(0);
            setRace(r => (r.hasStarted || r.paused || r.underStartersOrders
                ? { ...r, hasStarted: false, paused: false, underStartersOrders: false }
                : r));
        }

        // Race/session state persistence is owned by lapdata (server-side), so the
        // display no longer POSTs transitions — it is purely a viewer now.

        // FastestLap sessions: pass raw state to FastestLapCounter; skip driver-card update
        if (raceState.session_type === 'FastestLap') {
            setFastestLapRaceState(raceState);
            if (state === 'ArmedForStart') {
                setStartLightsShown(true);
                setLightsOut(false);
                setRace(r => ({ ...r, underStartersOrders: true }));
            } else if (state === 'Running') {
                setLightsOut(true);
                setRace(r => ({ ...r, hasStarted: true, paused: false, underStartersOrders: false }));
            } else if (state === 'Yellow' || state === 'Paused') {
                setRace(r => ({ ...r, paused: true }));
            } else if (state === 'Finished') {
                setRace(r => ({ ...r, hasStarted: false, paused: false }));
            }
            return;
        }

        const raceDrivers = raceState.drivers ?? [];
        const p1Driver = raceDrivers.find(d => d.position === 1);
        const p1LapsRemaining = p1Driver?.laps_remaining ?? 0;

        // Every card comes from lapdata's lineup, a staged one included, so a NextRace
        // edit (lapdata re-stages on reload_lineup) shows up here with no refetch.
        setDrivers(currentDrivers =>
            currentDrivers.map(driver => {
                if (!driver) return null;
                const rd = raceDrivers.find(d => d.lane === driver.number);
                // Not in lapdata's lineup: take it out of the preview too, or its stale
                // position puts it in a slot another driver's card now occupies.
                if (!rd) return { ...driver, hasStartedRacing: false, inLineup: false, position: null };
                return {
                    ...driver,
                    inLineup: true,
                    driverId: rd.driver_id,
                    name: rd.driver_name,
                    // lapdata publishes the lineup's car picture, so a Finished race keeps
                    // its cars after the session has ended. An older lapdata sends none.
                    carImgUrl: rd.car_picture !== undefined ? carImageUrl(rd.car_picture) : driver.carImgUrl,
                    lastLap: rd.has_started ? rd.last_lap.toFixed(3) : '',
                    fastestLap: rd.best_lap != null ? rd.best_lap.toFixed(3) : '',
                    isRaceFastestLap: rd.is_race_fastest_lap,
                    lapsRemaining: rd.laps_remaining,
                    lapsCompleted: rd.laps_completed,
                    totalRaceTime: rd.total_race_time > 0 ? rd.total_race_time.toFixed(3) : null,
                    position: rd.position,
                    finished: rd.finished,
                    suspended: rd.suspended,
                    hasStartedRacing: rd.has_started,
                    penaltyNotice: rd.penalty_notice,
                    p1LapsRemaining,
                };
            })
        );

        if (state === 'ArmedForStart') {
            setStartLightsShown(true);
            setLightsOut(false);
            setRace(r => ({ ...r, underStartersOrders: true }));
        } else if (state === 'Running') {
            setLightsOut(true);
            setRace(r => ({ ...r, hasStarted: true, paused: false, underStartersOrders: false }));
        } else if (state === 'Yellow' || state === 'Paused') {
            setRace(r => ({ ...r, paused: true }));
        } else if (state === 'Finished') {
            setRace(r => ({ ...r, hasStarted: false, paused: false }));
        }
    }

    // Driver cards fly in from the right and the group of *visible* cards stays
    // centred by shifting the container left by (6 - N) * 160px, where N is the
    // number of cards on screen. race_state gives started drivers contiguous slots
    // 1..N, so N is simply the count of cards currently shown. The show-condition is
    //   !underStartersOrders && (hasStartedRacing || (previewDriverCards && inLineup))
    // so N must be counted the same way. Falls back to 6 so the layout never
    // collapses to 0.
    // Any lost link means laps can't be counted, so it takes the whole screen. One at a
    // time, the most fundamental first: each one below also explains those after it.
    const fault = !apiReachable ? {}
        : !lapdataAlive ? { message: 'The lap counter has stopped responding — waiting for it to come back…' }
        : !trackOnline ? { heading: 'Track offline', message: 'Lost contact with the track — laps are not being counted. Stop racing.' }
        : null;

    const shownDriverCount = race.underStartersOrders
        ? 0
        : drivers.filter(d => d?.hasStartedRacing || (previewDriverCards && d?.inLineup)).length;
    const numberOfDriversRacingClassName = `numberOfDriversRacing${shownDriverCount || 6}`;
    return (
        <div id="top">

            <div id={'lapcounter'}>
                <MqttSubscriber
                    mqttHost={MQTT_URL}
                    onRaceStateMessage={processRaceStateMsg}
                    onLayer1StatusMessage={setLayer1Status}
                    debug={DEBUG}
                />
                <Header
                    sessionNumber={sessionNumber}
                    raceNumber={raceNumber}
                    sessionRacesTotal={sessionRacesTotal}
                    racePhase={racePhase}
                />
                {/* Shown through the whole yellow flag — the grace period (Yellow) and the
                    power cut after it (Paused) — hiding positions until it clears. */}
                <YellowFlagRacePaused
                    showMe={race.paused}
                    secondsLeft={yellowSecondsLeft}
                />
                <ApiUnreachableModal showMe={fault != null} {...fault} />
                <SoundBlockedModal armed={startLightsShown} />
                <StartLights
                    showMe={startLightsShown}
                    onClose={() => { setStartLightsShown(false); setLightsOut(false); setStartLights(0); }}
                    lightsOut={lightsOut}
                    startLights={startLights}
                />
                {sessionType === 'FastestLap' ? (
                    <FastestLapCounter
                        raceState={fastestLapRaceState}
                        pendingRace={pendingRace}
                    />
                ) : (
                    <div id="driverCardOuter">
                        <div id="driverCardContainer" className={numberOfDriversRacingClassName}>
                            <DriverCard driver={drivers[0]} underStartersOrders={race.underStartersOrders} previewDriverCards={previewDriverCards} />
                            <DriverCard driver={drivers[1]} underStartersOrders={race.underStartersOrders} previewDriverCards={previewDriverCards} />
                            <DriverCard driver={drivers[2]} underStartersOrders={race.underStartersOrders} previewDriverCards={previewDriverCards} />
                            <DriverCard driver={drivers[3]} underStartersOrders={race.underStartersOrders} previewDriverCards={previewDriverCards} />
                            <DriverCard driver={drivers[4]} underStartersOrders={race.underStartersOrders} previewDriverCards={previewDriverCards} />
                            <DriverCard driver={drivers[5]} underStartersOrders={race.underStartersOrders} previewDriverCards={previewDriverCards} />
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

export default LapCounter;
