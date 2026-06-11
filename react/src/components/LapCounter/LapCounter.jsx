import './LapCounter.css';
import useLocalStorageState from 'use-local-storage-state'
import MqttSubscriber from '../MqttSubscriber.jsx'
import EditDriverNamesModal from './EditDriverNamesModal.jsx';
import CarSelectorModal from './CarSelectorModal.jsx';
import DriverCard from './DriverCard.jsx';
import Header from './Header.jsx';
import StartRaceModal from './StartRaceModal.jsx';
import StartLights from './StartLights.jsx';
import { useState, useRef, useEffect } from 'react';
import { useLoaderData } from 'react-router-dom';
import { defaultConfig, defaultRace, getDriverDataDefault, getInitialDrivers } from '../../defaultConfig.js';

const DEBUG = true;

const LapCounter = () => {
    const pendingRace = useLoaderData();

    const [config, setConfig] = useLocalStorageState('config', {defaultValue: {...defaultConfig}});
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

    const mqttClientRef = useRef(null);
    const prevRaceStateRef = useRef(null);

    // Seed driver names and raceId from pending race on page load
    useEffect(() => {
        if (!pendingRace?.lane_assignments) return;
        if (pendingRace.race_id) setRaceId(pendingRace.race_id);
        setDrivers(current =>
            current.map(driver => {
                const a = pendingRace.lane_assignments.find(
                    a => a.lane_number === driver.number && a.id !== 0
                );
                return a ? { ...driver, name: a.driver_name, driverId: a.id, carImgUrl: carImageUrl(a.car_picture) } : driver;
            })
        );
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    const [startRaceModalShown, setStartRaceModalShown] = useState(false);
    const [startLightsShown, setStartLightsShown] = useState(false);
    const [lightsOut, setLightsOut] = useState(false);
    const [previewDriverCards, setPreviewDriverCards] = useState(false);

    const storeMqttHost = (newMqttHost) => {
        setConfig({...config, mqtturl: newMqttHost});
    }

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

    // Green flag clicked: fetch lineup, reset driver stats, show Start popup
    const handleGreenFlag = async () => {
        const laps = race.type?.details.laps ?? defaultRace.type.details.laps;

        let assignmentByLane = {};
        try {
            const res = await fetch(`${config.apiurl}/races/pending/`);
            if (res.ok) {
                const pendingRace = await res.json();
                if (pendingRace.race_id) setRaceId(pendingRace.race_id);
                if (pendingRace.race_number) setRaceNumber(pendingRace.race_number);
                for (const a of pendingRace.lane_assignments ?? []) {
                    if (a.id !== 0 && a.lane_enabled) {
                        assignmentByLane[a.lane_number] = a;
                    }
                }
            }
        } catch (e) {
            console.error('Failed to load pending race:', e);
        }

        setDrivers(currentDrivers => {
            let nextPosition = 1;
            return currentDrivers.map((driver, index) => {
                const laneNumber = index + 1;
                const a = assignmentByLane[laneNumber];
                if (!a) return null;
                return {
                    ...(driver ?? { number: laneNumber }),
                    ...getDriverDataDefault(laps),
                    lapsRemaining: laps,
                    p1LapsRemaining: laps,
                    position: nextPosition++,
                    name: a.driver_name,
                    driverId: a.id,
                    carImgUrl: carImageUrl(a.car_picture),
                };
            });
        });

        if (mqttClientRef.current) {
            mqttClientRef.current.publish('race_control', JSON.stringify({
                command: 'prepare',
                race_id: raceIdRef.current,
            }));
        }

        setPreviewDriverCards(true);
        setStartRaceModalShown(true);
    };

    // Start button in popup: arm the race — lapdata controls the random delay and lights out
    const handleRaceStart = () => {
        setStartRaceModalShown(false);
        setPreviewDriverCards(false);
        setRace({ ...defaultRace, underStartersOrders: true, type: race.type });

        const targetLaps = race.type?.details.laps ?? 20;
        if (mqttClientRef.current && raceIdRef.current) {
            mqttClientRef.current.publish('race_control', JSON.stringify({
                command: 'arm',
                race_id: raceIdRef.current,
                target_laps: targetLaps,
            }));
        }
    };

    const handleRaceEnd = () => {
        if (mqttClientRef.current) {
            mqttClientRef.current.publish('race_control', JSON.stringify({ command: 'end' }));
        }
        setRace({...race, underStartersOrders: false, hasStarted: false, paused: false});
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
        const { state, drivers: raceDrivers, race_fastest_lap } = raceState;

        const prevState = prevRaceStateRef.current;
        prevRaceStateRef.current = state;
        if (raceIdRef.current) {
            if (state === 'Running' && prevState !== 'Running') {
                fetch(`${config.apiurl}/races/${raceIdRef.current}/start`, { method: 'POST' }).catch(() => {});
            } else if (state === 'Finished' && prevState !== 'Finished') {
                fetch(`${config.apiurl}/races/${raceIdRef.current}/finish`, { method: 'POST' }).catch(() => {});
            }
        }

        // Keep raceId in sync with what LapData is tracking (needed for car-swap calls)
        if (raceState.race_id && raceState.race_id !== raceIdRef.current) {
            setRaceId(raceState.race_id);
        }
        // race_number is now published directly by LapData — use it as the source of truth
        if (raceState.race_number) {
            setRaceNumber(raceState.race_number);
        }

        if (race_fastest_lap && race_fastest_lap < Number(statsRef.current.fastestLapToday)) {
            storeFastestLapToday(race_fastest_lap.toFixed(3));
        }

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
                    raceNumber={raceNumber}
                    mqttHost={config.mqtturl}
                    setMqtthost={storeMqttHost}
                    onGreenFlag={handleGreenFlag}
                    fastestLapToday={statsRef.current.fastestLapToday}
                    hasStarted={race.hasStarted}
                    underStartersOrders={race.underStartersOrders || startRaceModalShown}
                    onRaceEnd={handleRaceEnd}
                    yellowFlagAdvantageDuration={3.8}
                    onYellowFlagCountdown={() => { console.log('Lapcounter: Yellow Flag Countdown')}}
                    onYellowFlag={() => {
                        setRace({...race, paused: true});
                        mqttClientRef.current?.publish('race_control', JSON.stringify({ command: 'pause' }));
                    }}
                    onEndYellowFlag={() => {
                        setRace({...race, paused: false});
                        mqttClientRef.current?.publish('race_control', JSON.stringify({ command: 'resume' }));
                    }}
                    resetFastestLapToday={resetFastestLapToday}
                />
                <StartRaceModal
                    showMe={startRaceModalShown}
                    onStart={handleRaceStart}
                    onClose={() => setStartRaceModalShown(false)}
                />
                <StartLights
                    showMe={startLightsShown}
                    onClose={() => { setStartLightsShown(false); setLightsOut(false); }}
                    lightsOut={lightsOut}
                />
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
