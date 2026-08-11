import './LapCounter.css';
import useLocalStorageState from 'use-local-storage-state'
import MqttSubscriber from '../MqttSubscriber.jsx'
import EditDriverNamesModal from './EditDriverNamesModal.jsx';
import CarSelectorModal from './CarSelectorModal.jsx';
import DriverCard from './DriverCard.jsx';
import FastestLapCounter from './FastestLapCounter.jsx';
import Header from './Header.jsx';
import StartLights from './StartLights.jsx';
import YellowFlagRacePaused from './YellowFlagRacePaused.jsx';
import { useState, useRef, useEffect } from 'react';
import { useLoaderData } from 'react-router-dom';
import { defaultConfig, defaultRace, getInitialDrivers } from '../../defaultConfig.js';

const DEBUG = true;

const LapCounter = () => {
    const pendingRace = useLoaderData();

    const [config] = useLocalStorageState('config', {defaultValue: {...defaultConfig}});
    console.log('config', config);

    const [race, setRace] = useState(defaultRace);

    const [stats, setStats] = useLocalStorageState('stats', {defaultValue: {
        fastestLapToday: '99.999',
        fastestLapTodayUpdatedOn: Date()
    }});
    const statsRef = useRef();
    statsRef.current = stats;

    const lapsPerRace = race.RaceType?.details.laps ?? 0;

    const carMediaBase = config.apiurl.replace(/\/$/, '') + "/" + config.carmediafolder.replace(/\/$/, '');
    const defaultCarImg = carMediaBase + '/GT_AA_Generic.jpg';
    // Build a car image URL from a picture filename (from the pending race lineup),
    // falling back to the generic image when no car is assigned.
    const carImageUrl = (picture) => picture ? `${carMediaBase}/${picture}` : defaultCarImg;
    const initialDrivers = getInitialDrivers(lapsPerRace, defaultCarImg);
    const [drivers, setDrivers] = useState([...initialDrivers]);

    const [driverNamesModalShown, setDriverNamesModalShown] = useState(false);
    const [driverNamesModalDriverIdx, setDriverNamesModalDriverIdx] = useState(0);

    const [carSelectorModalShown, setCarSelectorModalShown] = useState(false);
    const [carSelectorModalDriverIdx, setCarSelectorModalDriverIdx] = useState(0);

    const [raceId, setRaceId] = useState(null);
    const raceIdRef = useRef();
    raceIdRef.current = raceId;

    const [raceNumber, setRaceNumber] = useState(pendingRace?.race_number ?? null);
    const [sessionNumber, setSessionNumber] = useState(pendingRace?.session_number ?? null);
    const [sessionRacesTotal, setSessionRacesTotal] = useState(pendingRace?.session_races_total ?? null);
    const [sessionType, setSessionType] = useState(pendingRace?.session_type ?? 'Points');
    const [fastestLapRaceState, setFastestLapRaceState] = useState(null);

    const mqttClientRef = useRef(null);
    const resyncInFlightRef = useRef(false);

    // Apply a race setup (from the loader / /races/current/) to the viewmodel:
    // identity (id, number, type) + a *staged* lane lineup. Driver cards are rebuilt
    // from a fresh base so no lap times / laps-remaining bleed across from a previous
    // race — live lap data only ever comes from race_state. `targetLaps` (from the
    // race_state) seeds "Laps Remaining" with the full race distance before any laps
    // are run; it falls back to the local race config when unknown.
    const applyRaceSetup = (setup, targetLaps) => {
        if (!setup?.lane_assignments) return;
        setDrivers(
            getInitialDrivers(targetLaps ?? lapsPerRace, defaultCarImg).map(driver => {
                const a = setup.lane_assignments.find(
                    a => a.lane_number === driver.number && a.id !== 0
                );
                return a ? { ...driver, name: a.driver_name, driverId: a.id, carImgUrl: carImageUrl(a.car_picture) } : driver;
            })
        );
        if (setup.race_id) setRaceId(setup.race_id);
        if (setup.race_number != null) setRaceNumber(setup.race_number);
        if (setup.session_number != null) setSessionNumber(setup.session_number);
        if (setup.session_races_total != null) setSessionRacesTotal(setup.session_races_total);
        if (setup.session_type) setSessionType(setup.session_type);
    };

    // Stage a freshly-loaded race onto the get-ready preview: clean lineup (above)
    // plus reset race-phase UI. Used when lapdata stages a new race — e.g. "Next
    // Race" on /racecontrol — so /currentrace immediately shows the new lineup
    // instead of leaving the finished leaderboard on screen.
    const stageRace = (setup, targetLaps) => {
        applyRaceSetup(setup, targetLaps);
        setRacePhase('getready');
        setPreviewDriverCards(true);
        setStartLightsShown(false);
        setLightsOut(false);
        setStartLights(0);
        setRace(r => ({ ...r, hasStarted: false, paused: false, underStartersOrders: false }));
    };

    // The DB is authoritative for which race is current. When a race_state arrives
    // for a race other than the one we're showing, re-fetch /races/current/ to decide
    // whether to adopt it (newly staged) or ignore it (stale lapdata broadcast).
    // A NotStarted state means lapdata just staged a new race, so reset to the clean
    // get-ready preview; otherwise overlay identity/lineup onto the live view.
    const resyncCurrentRace = (incomingState, targetLaps) => {
        if (resyncInFlightRef.current) return;
        resyncInFlightRef.current = true;
        fetch(`${config.apiurl}/races/current/`)
            .then(r => r.ok ? r.json() : null)
            .then(setup => {
                if (!setup) return;
                if (incomingState === 'NotStarted') stageRace(setup, targetLaps);
                else applyRaceSetup(setup, targetLaps);
            })
            .catch(() => {})
            .finally(() => { resyncInFlightRef.current = false; });
    };

    // Seed identity + lineup from the current race on page load
    useEffect(() => {
        applyRaceSetup(pendingRace);
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // Ask lapdata for the current state on load — race_state is not retained on the broker.
    useEffect(() => {
        const t = setTimeout(() => {
            mqttClientRef.current?.publish('race_control', JSON.stringify({ command: 'status' }));
        }, 800);
        return () => clearTimeout(t);
    }, []);

    const [racePhase, setRacePhase] = useState(pendingRace?.lane_assignments ? 'getready' : null);
    const [startLightsShown, setStartLightsShown] = useState(false);
    const [lightsOut, setLightsOut] = useState(false);
    const [startLights, setStartLights] = useState(0); // lit count, driven by lapdata's race_state
    const [previewDriverCards, setPreviewDriverCards] = useState(!!pendingRace?.lane_assignments);

    const storeFastestLapToday = (lapTime) => {
        setStats({...statsRef.current,
            fastestLapToday: lapTime,
            fastestLapTodayUpdatedOn: Date()
        });
    }

    const resetExpiredFastestLapToday = () => {
        const fastestLapTodayUpdatedOnDate = new Date(statsRef.current.fastestLapTodayUpdatedOn).getTime();
        const now = new Date();
        const twentyFourhoursAgo = now.setDate(now.getDate() - 1);
        const fastestLapToday = statsRef.current.fastestLapToday;

        if (fastestLapToday === '' || fastestLapToday === null || fastestLapTodayUpdatedOnDate < twentyFourhoursAgo) {
            resetFastestLapToday();
        }
    }

    const resetFastestLapToday = () => {
        storeFastestLapToday("99.999");
    }

    resetExpiredFastestLapToday();

    const openDriverNamesModal = (driverIdx) => {
        setDriverNamesModalDriverIdx(driverIdx);
        setDriverNamesModalShown(true);
    }

    const openCarSelectorModal = (driverIdx) => {
        setCarSelectorModalDriverIdx(driverIdx);
        setCarSelectorModalShown(true);
    }

    const closeCarSelectorModal = () => {
        setCarSelectorModalShown(false);
    }

    const handleCarSelectedInLapCounter = (car) => {
        const laneNumber = drivers[carSelectorModalDriverIdx].number;
        if (raceIdRef.current) {
            fetch(`${config.apiurl}/races/${raceIdRef.current}/lanes/${laneNumber}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ car_id: car.id }),
            }).catch(e => console.error('Failed to save car assignment:', e));
        }
    }

    // Primary display update: map race_state from LapData onto the drivers viewmodel
    const processRaceStateMsg = (raceState) => {
        const { state, race_fastest_lap } = raceState;

        // Reconcile identity against the DB (authoritative for which race is
        // current). A race_state for a different race than the one we're showing is
        // either a newly-staged race or a stale lapdata broadcast — re-fetch the
        // current race to arbitrate, and don't apply this (possibly stale) message.
        if (raceState.race_id && raceState.race_id !== raceIdRef.current) {
            resyncCurrentRace(raceState.state, raceState.target_laps);
            return;
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

        // Header phase + (Points) staged-lineup preview, driven by the live state.
        if (state === 'Finished') setRacePhase('results');
        else if (state === 'NotStarted') setRacePhase('getready');
        else setRacePhase('live');
        if (state === 'NotStarted') setPreviewDriverCards(true);
        else if (state === 'Running' || state === 'Finished') setPreviewDriverCards(false);

        // Race/session state persistence is owned by lapdata (server-side), so the
        // display no longer POSTs transitions — it is purely a viewer now.

        if (race_fastest_lap && race_fastest_lap < Number(statsRef.current.fastestLapToday)) {
            storeFastestLapToday(race_fastest_lap.toFixed(3));
        }

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
            } else if (state === 'Paused') {
                setRace(r => ({ ...r, paused: true }));
            } else if (state === 'Finished') {
                setRace(r => ({ ...r, hasStarted: false, paused: false }));
            }
            return;
        }

        const raceDrivers = raceState.drivers ?? [];
        const p1Driver = raceDrivers.find(d => d.position === 1);
        const p1LapsRemaining = p1Driver?.laps_remaining ?? 0;

        setDrivers(currentDrivers =>
            currentDrivers.map(driver => {
                if (!driver) return null;
                const rd = raceDrivers.find(d => d.lane === driver.number);
                if (!rd) return { ...driver, hasStartedRacing: false };
                return {
                    ...driver,
                    name: rd.driver_name,
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
        } else if (state === 'Paused') {
            setRace(r => ({ ...r, paused: true }));
        } else if (state === 'Finished') {
            setRace(r => ({ ...r, hasStarted: false, paused: false }));
        }
    }

    // Driver cards fly in from the right and the group of *visible* cards stays
    // centred by shifting the container left by (6 - N) * 160px, where N is the
    // number of cards on screen. race_state gives started drivers contiguous slots
    // 1..N, so N is simply the count of cards currently shown. The show-condition is
    //   !underStartersOrders && (hasStartedRacing || previewDriverCards)
    // so N must be counted the same way. Falls back to 6 so the layout never
    // collapses to 0.
    const shownDriverCount = race.underStartersOrders
        ? 0
        : (previewDriverCards ? drivers.filter(Boolean).length : drivers.filter(d => d?.hasStartedRacing).length);
    const numberOfDriversRacingClassName = `numberOfDriversRacing${shownDriverCount || 6}`;
    return (
        <div id="top">

            <div id={'lapcounter'}>
                <MqttSubscriber
                    mqttHost={config.mqtturl}
                    onRaceStateMessage={processRaceStateMsg}
                    clientRef={mqttClientRef}
                    debug={DEBUG}
                />
                <Header
                    sessionNumber={sessionNumber}
                    raceNumber={raceNumber}
                    sessionRacesTotal={sessionRacesTotal}
                    racePhase={racePhase}
                />
                <YellowFlagRacePaused
                    showMe={race.paused}
                    onRacePaused={() => {}}
                    onEndYellowFlag={() => {}}
                />
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
                            <DriverCard driver={drivers[0]} underStartersOrders={race.underStartersOrders} previewDriverCards={previewDriverCards} onRequestOpenDriverNames={() => {openDriverNamesModal(0)}} onRequestOpenCarSelector={() => {openCarSelectorModal(0)}} />
                            <DriverCard driver={drivers[1]} underStartersOrders={race.underStartersOrders} previewDriverCards={previewDriverCards} onRequestOpenDriverNames={() => {openDriverNamesModal(1)}} onRequestOpenCarSelector={() => {openCarSelectorModal(1)}} />
                            <DriverCard driver={drivers[2]} underStartersOrders={race.underStartersOrders} previewDriverCards={previewDriverCards} onRequestOpenDriverNames={() => {openDriverNamesModal(2)}} onRequestOpenCarSelector={() => {openCarSelectorModal(2)}} />
                            <DriverCard driver={drivers[3]} underStartersOrders={race.underStartersOrders} previewDriverCards={previewDriverCards} onRequestOpenDriverNames={() => {openDriverNamesModal(3)}} onRequestOpenCarSelector={() => {openCarSelectorModal(3)}} />
                            <DriverCard driver={drivers[4]} underStartersOrders={race.underStartersOrders} previewDriverCards={previewDriverCards} onRequestOpenDriverNames={() => {openDriverNamesModal(4)}} onRequestOpenCarSelector={() => {openCarSelectorModal(4)}} />
                            <DriverCard driver={drivers[5]} underStartersOrders={race.underStartersOrders} previewDriverCards={previewDriverCards} onRequestOpenDriverNames={() => {openDriverNamesModal(5)}} onRequestOpenCarSelector={() => {openCarSelectorModal(5)}} />

                            <CarSelectorModal
                                showMe={carSelectorModalShown}
                                onClose={closeCarSelectorModal}
                                carImgListUrl={config.apiurl + '/api/cars'}
                                drivers={drivers}
                                setDrivers={setDrivers}
                                driverIdx={carSelectorModalDriverIdx}
                                setDriverIdx={setCarSelectorModalDriverIdx}
                                onCarSelected={handleCarSelectedInLapCounter}
                            />
                        </div>
                    </div>
                )}
            </div>

           <EditDriverNamesModal
                showMe={driverNamesModalShown}
                onClose={() => setDriverNamesModalShown(false)}
                drivers={drivers}
                setDrivers={setDrivers}
                driverIdxToFocus={driverNamesModalDriverIdx}
            />
        </div>
    );
}

export default LapCounter;
