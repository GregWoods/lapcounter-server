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
    console.log('VITE_CIRCUIT_NAME', import.meta.env.VITE_CIRCUIT_NAME);
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

    const defaultCarImg = config.apiurl.replace(/\/$/, '') + "/" + config.carmediafolder.replace(/\/$/, '') + '/GT_AA_Generic.jpg';
    console.log('defaultCarImg', defaultCarImg);
    const initialDrivers = getInitialDrivers(lapsPerRace, defaultCarImg);
    const [drivers, setDrivers] = useState([...initialDrivers]);

    const [driverNamesModalShown, setDriverNamesModalShown] = useState(false);
    const [driverNamesModalDriverIdx, setDriverNamesModalDriverIdx] = useState(0);

    const [carSelectorModalShown, setCarSelectorModalShown] = useState(false);
    const [carSelectorModalDriverIdx, setCarSelectorModalDriverIdx] = useState(0);

    const [raceId, setRaceId] = useState(null);
    const raceIdRef = useRef();
    raceIdRef.current = raceId;

    const mqttClientRef = useRef(null);

    // Seed driver names and raceId from pending race on page load
    useEffect(() => {
        if (!pendingRace?.lane_assignments) return;
        if (pendingRace.race_id) setRaceId(pendingRace.race_id);
        setDrivers(current =>
            current.map(driver => {
                const a = pendingRace.lane_assignments.find(
                    a => a.lane_number === driver.number && a.id !== 0
                );
                return a ? { ...driver, name: a.driver_name, driverId: a.id } : driver;
            })
        );
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    const [startRaceModalShown, setStartRaceModalShown] = useState(false);
    const [startLightsShown, setStartLightsShown] = useState(false);
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
                for (const a of pendingRace.lane_assignments ?? []) {
                    if (a.id !== 0) assignmentByLane[a.lane_number] = a;
                }
            }
        } catch (e) {
            console.error('Failed to load pending race:', e);
        }

        setDrivers(currentDrivers =>
            currentDrivers.map(driver => {
                const a = assignmentByLane[driver.number];
                return {
                    ...driver,
                    ...getDriverDataDefault(laps),
                    lapsRemaining: laps,
                    p1LapsRemaining: laps,
                    position: driver.number,
                    ...(a && { name: a.driver_name, driverId: a.id }),
                };
            })
        );

        setPreviewDriverCards(true);
        setStartRaceModalShown(true);
    };

    // Start button in popup: close popup and preview, show start lights
    const handleRaceStart = () => {
        setStartRaceModalShown(false);
        setPreviewDriverCards(false);
        setStartLightsShown(true);
        setRace({ ...defaultRace, underStartersOrders: true, type: race.type });
        if (raceId) {
            fetch(`${config.apiurl}/races/${raceId}/start`, { method: 'POST' })
                .catch(e => console.error('Failed to mark race as started:', e));
        }
    };

    // Lights out: publish race_control start — LapData owns the race from here
    const handleGoGoGo = () => {
        setStartLightsShown(false);
        setRace({...race,
            underStartersOrders: false,
            hasStarted: true,
            paused: false
        });

        const targetLaps = race.type?.details.laps ?? 20;
        if (mqttClientRef.current && raceIdRef.current) {
            mqttClientRef.current.publish('race_control', JSON.stringify({
                command: 'start',
                race_id: raceIdRef.current,
                target_laps: targetLaps,
            }));
        }
    }

    const handleRaceEnd = () => {
        if (mqttClientRef.current) {
            mqttClientRef.current.publish('race_control', JSON.stringify({ command: 'end' }));
        }
        if (raceIdRef.current) {
            fetch(`${config.apiurl}/races/${raceIdRef.current}/finish`, { method: 'POST' })
                .catch(e => console.error('Failed to mark race as finished:', e));
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

    // Primary display update: map race_state from LapData onto the drivers viewmodel
    const processRaceStateMsg = (raceState) => {
        const { state, drivers: raceDrivers, race_fastest_lap } = raceState;

        if (race_fastest_lap && race_fastest_lap < Number(statsRef.current.fastestLapToday)) {
            storeFastestLapToday(race_fastest_lap.toFixed(3));
        }

        const p1Driver = raceDrivers.find(d => d.position === 1);
        const p1LapsRemaining = p1Driver?.laps_remaining ?? 0;

        setDrivers(currentDrivers =>
            currentDrivers.map(driver => {
                const rd = raceDrivers.find(d => d.lane === driver.number);
                if (!rd) return driver;
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

        const numberOfDriversRacing = raceDrivers.length;
        if (state === 'Running') {
            setRace(r => ({ ...r, hasStarted: true, paused: false, numberOfDriversRacing }));
        } else if (state === 'Paused') {
            setRace(r => ({ ...r, paused: true, numberOfDriversRacing }));
        } else if (state === 'Finished') {
            setRace(r => ({ ...r, hasStarted: false, paused: false, numberOfDriversRacing }));
            if (raceIdRef.current) {
                fetch(`${config.apiurl}/races/${raceIdRef.current}/finish`, { method: 'POST' })
                    .catch(e => console.error('Failed to mark race as finished:', e));
            }
        }
    }

    const numberOfDriversRacingClassName = `numberOfDriversRacing${race.numberOfDriversRacing}`;
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
                    circuitName={config.circuitname}
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
                    onClose={() => setStartLightsShown(false)}
                    onLightsOut={handleGoGoGo}
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
