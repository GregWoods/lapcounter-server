import './LapCounter.css';
import useLocalStorageState from 'use-local-storage-state'
import MqttSubscriber from '../MqttSubscriber.jsx'
import EditDriverNamesModal from './EditDriverNamesModal.jsx';
import CarSelectorModal from './CarSelectorModal.jsx';
import DriverCard from './DriverCard.jsx';
import Header from './Header.jsx';
import { useState, useRef } from 'react';
import {modifyDriversViewModel, calculateLapTime, checkEndOfRace} from './lapUtils.js';
import { defaultConfig, defaultRace, lapDataDefault, getDriverDataDefault, getInitialDrivers } from '../../defaultConfig.js';

const DEBUG = true;

const LapCounter = () => {
    console.log('VITE_CIRCUIT_NAME', import.meta.env.VITE_CIRCUIT_NAME);
    //TODO: split true environment settings from advanced user  focused settings

    //console.log('defaultConfig', defaultConfig);

    // Using refs...
    //  see: https://stackoverflow.com/questions/57847594/react-hooks-accessing-up-to-date-state-from-within-a-callback
    //  Each of the following values which are "ref'd up" are used inside the processLaps callback.
    //    If we didn't use Refs (or some similar technique), then referring to the state
    //    variables would always return the initial value rather than the current value.

    const [config, setConfig] = useLocalStorageState('config', {defaultValue: {...defaultConfig}});
    console.log('config', config);

    const [race, setRace] = useLocalStorageState('race', {defaultValue: defaultRace});
    const raceRef = useRef();
    raceRef.current = race;

    const [stats, setStats] = useLocalStorageState('stats', {defaultValue: {
        fastestLapToday: '99.999', 
        fastestLapTodayUpdatedOn: Date()
    }});
    const statsRef = useRef();
    statsRef.current = stats;

    const [lapData, setLapData] = useLocalStorageState('lap', {defaultValue: [...lapDataDefault]});
    const lapDataRef = useRef();
    lapDataRef.current = lapData;

    const lapsPerRace = raceRef.current.RaceType?.details.laps ?? 0;

    const defaultCarImg = config.apiurl.replace(/\/$/, '') + "/" + config.carmediafolder.replace(/\/$/, '') + '/GT_AA_Generic.jpg';
    console.log('defaultCarImg', defaultCarImg);
    const initialDrivers = getInitialDrivers(lapsPerRace, defaultCarImg);
    const [drivers, setDrivers] = useLocalStorageState('drivers', {defaultValue: [...initialDrivers]});
    const driversRef = useRef();
    driversRef.current = drivers;

    //Normal state variables for simple, non persistent state, such as dialog open state
    const [driverNamesModalShown, setDriverNamesModalShown] = useState(false);
    const [driverNamesModalDriverIdx, setDriverNamesModalDriverIdx] = useState(0);

    const [carSelectorModalShown, setCarSelectorModalShown] = useState(false);
    const [carSelectorModalDriverIdx, setCarSelectorModalDriverIdx] = useState(0);

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
        //  reset lap record if it is more than 24h old
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

    const handleStartCountdown = (raceTypeObj) => {
        //reset all appropriate values ready for race start
        resetDrivers(raceTypeObj);

        setRace({...defaultRace, 
            underStartersOrders: true,
            type: raceTypeObj
        });
    }

    const handleGoGoGo = () => {
        setRace({...raceRef.current, 
            underStartersOrders:false, 
            hasStarted:true, 
            paused:false
        });

        //ideally we'd set raceStartTime.current = wsMsg.time when the lights go out,
        //  but we don't have that time info which is obtained from the server side python.
        //  I don't want any more complexity in the server side code (at the moment)
        //  and I don't want to have to sync server and client times, so we stick
        //  with zoomroom's implementation, which is that the race timing doesn't start
        //  until the first car crosses the line.
    }

    const handleRaceEnd = () => {
        //must use raceRef.current here, as this is being called from the mqtt callback
        //  "race" will always be the initial values in this and similar callbacks
        setRace({...raceRef.current, 
            underStartersOrders:false, 
            hasStarted:false, 
            paused:false
        });
    }

    const resetDrivers = (raceTypeObj) => {
        setLapData([...lapDataDefault]);

        const newDrivers = [];
        for (const driver of drivers) {
            newDrivers.push({
                ...driver, 
                ...getDriverDataDefault(lapsPerRace), 
                lapsRemaining: raceTypeObj.details.laps, 
                p1LapsRemaining: raceTypeObj.details.laps
            });
        }
        setDrivers(newDrivers);
    }

    const openCarSelectorModal = (driverIdx) => {
        setCarSelectorModalDriverIdx(driverIdx);
        setCarSelectorModalShown(true);
    }

    const closeCarSelectorModal = () => {
        setCarSelectorModalShown(false);
        //TODO: unspotlight all drivers
    }

    //This is the callback from Mqtt, so like a setInterval, it lives outside of the React lifecycle
    //  Hence we need to use useRef to access the current state values
    const processLapMsg = (lapMsg) => {
        console.log("INCOMING LAP DATA: ", lapMsg)
        if (!raceRef.current.hasStarted || raceRef.current.paused) { return }
        
        const carIdx = lapMsg.car - 1;
        const laps = lapDataRef.current
        const oldLap = laps[carIdx];
        
        //convert websocket message into useful lap data
        //console.log("==ProcessMessage, car:" + lapMsg.car);

        let [newLap, newRace] = calculateLapTime(
            lapMsg, 
            oldLap, 
            raceRef.current);

        laps[carIdx] = newLap;
        setLapData(laps);

        //Fastest lap of this race
        console.log(`newLap.bestLapTime: ${newLap.bestLapTime} :::: Number(newRace.fastestLap): ${Number(newRace.fastestLap)}`);
        if (newLap.bestLapTime < Number(newRace.fastestLap)) {
            newRace.fastestLap = newLap.bestLapTime.toFixed(3);
        }

        //Fastest lap of the day
        console.log(`newLap.bestLapTime: ${newLap.bestLapTime} :::: Number(fastestLapToday): ${Number(statsRef.current.fastestLapToday)}`);
        if (newLap.bestLapTime < Number(statsRef.current.fastestLapToday)) {
            storeFastestLapToday(newLap.bestLapTime.toFixed(3));
        }

        console.log(`newRace.startTime: ${newRace.startTime}`)
        //create "drivers" view-model from lap data
        const modifiedDrivers = modifyDriversViewModel(
                driversRef.current, 
                carIdx, 
                newLap, 
                raceRef.current.type.details.laps, 
                newRace.fastestLap,
                newRace.startTime
        );
        setDrivers(modifiedDrivers);

        const numberOfDriversRacing = modifiedDrivers.reduce((acc, driver) => {
            return acc + Number(driver.hasStartedRacing);
        }, 0);
        console.log(`Number of Drivers Racing: ${numberOfDriversRacing}`);
        newRace.numberOfDriversRacing = numberOfDriversRacing;

        setRace(newRace);

        checkEndOfRace(modifiedDrivers, handleRaceEnd);
    }


    const handleRaceTypeChange = (raceTypeObj) => {
        console.log("++++++++++++++ LapCounter:handleRaceTypeChange", raceTypeObj);
        setRace({...raceRef.current, type: raceTypeObj});
    }

    const numberOfDriversRacingClassName = `numberOfDriversRacing${race.numberOfDriversRacing}`; 
    return (
        <div id="top">

            <div id={'lapcounter'}>
                <MqttSubscriber mqttHost={config.mqtturl} onIncomingLapMessage={processLapMsg} debug={DEBUG} />
                <Header
                    circuitName={config.circuitname}
                    mqttHost={config.mqtturl}
                    setMqtthost={storeMqttHost}
                    onRaceTypeChange={handleRaceTypeChange}
                    onStartCountdown={handleStartCountdown}
                    onGoGoGo={handleGoGoGo}

                    fastestLapToday={statsRef.current.fastestLapToday}
                    hasStarted={race.hasStarted}
                    onRaceEnd={handleRaceEnd}
                    yellowFlagAdvantageDuration = {3.8}
                    onYellowFlagCountdown={() => { console.log('Lapcounter: Yellow Flag Countdown')}}
                    onYellowFlag={() => setRace({...race, paused: true})}
                    onEndYellowFlag={() => setRace({...race, paused: false})}
                    resetFastestLapToday = {resetFastestLapToday}
                />
                <div id="driverCardOuter">
                    <div id="driverCardContainer" className={numberOfDriversRacingClassName}>
                        <DriverCard driver={drivers[0]} underStartersOrders={race.underStartersOrders} onRequestOpenDriverNames={() => {openDriverNamesModal(0)}} onRequestOpenCarSelector={() => {openCarSelectorModal(0)}} />
                        <DriverCard driver={drivers[1]} underStartersOrders={race.underStartersOrders} onRequestOpenDriverNames={() => {openDriverNamesModal(1)}} onRequestOpenCarSelector={() => {openCarSelectorModal(1)}} />
                        <DriverCard driver={drivers[2]} underStartersOrders={race.underStartersOrders} onRequestOpenDriverNames={() => {openDriverNamesModal(2)}} onRequestOpenCarSelector={() => {openCarSelectorModal(2)}} />
                        <DriverCard driver={drivers[3]} underStartersOrders={race.underStartersOrders} onRequestOpenDriverNames={() => {openDriverNamesModal(3)}} onRequestOpenCarSelector={() => {openCarSelectorModal(3)}} />
                        <DriverCard driver={drivers[4]} underStartersOrders={race.underStartersOrders} onRequestOpenDriverNames={() => {openDriverNamesModal(4)}} onRequestOpenCarSelector={() => {openCarSelectorModal(4)}} />
                        <DriverCard driver={drivers[5]} underStartersOrders={race.underStartersOrders} onRequestOpenDriverNames={() => {openDriverNamesModal(5)}} onRequestOpenCarSelector={() => {openCarSelectorModal(5)}} />

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