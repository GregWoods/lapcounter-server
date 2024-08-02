import './LapCounter.css';
import useLocalStorageState from 'use-local-storage-state'
import MqttSubscriber from '../MqttSubscriber.jsx'
import EditDriverNamesModal from './EditDriverNamesModal.jsx';
import CarSelectorModal from './CarSelectorModal.jsx';
import DriverCard from './DriverCard.jsx';
import Header from './Header.jsx';
import { useState, useRef } from 'react';
import {modifyDriversViewModel, calculateLapTime, checkEndOfRace} from './lapUtils.js';


const DEBUG = true;


const LapCounter = () => {

    let defaultConfig = {
        // These defaults are based on the production docker setup
        // They are stored in localstorage
        mqtthost: "ws://192.168.8.3:8080",
        apihost: "http://192.168.8.3:5001",
        racepresets: [
            { id: 0, type: 'laps', description: 'Shakedown (6 laps)', details: { laps: 6 }},
            { id: 1, type: 'laps', description: 'Sprint (20 laps)', details: { laps: 20 }},
            { id: 2, type: 'laps', description: 'Standard (50 laps)', details: { laps: 50 }},
            { id: 3, type: 'laps', description: 'Professional (160 laps)', details: { laps: 160 }},
            /*{ id: 4, type: 'time', description: 'Endurance (60 minutes)', details: { time: '01:00:00' }},
            { id: 5, type: 'time', description: 'Le-Mans (4 hours)', details: { time: '04:00:00' }},
            { id: 6, type: 'lms', description: 'Last Man Standing\n(max 2 laps behind leader)', details: { maxLapsBehind: 2 }},*/
        ]
    }
    
    //developer defaults
    defaultConfig = {...defaultConfig,
        mqtthost: "ws://127.0.0.1:8080",
        apihost: "http://127.0.0.1:5001"
    };
    

    let defaultRace = { 
        firstCarCrossedStart: false,
        startTime: null,
        fastestLap: 99.999
    };

    const [config, setConfig] = useLocalStorageState('config', {defaultValue: defaultConfig});

    const [race, setRace] = useLocalStorageState('race', {defaultValue: defaultRace});
    const raceRef = useRef();
    raceRef.current = race;

    const [stats, setStats] = useLocalStorageState('stats', {defaultValue: {
        fastestLapToday: '99.999', 
        fastestLapTodayUpdatedOn: Date()
    }});
    const statsRef = useRef();
    statsRef.current = stats;

    const [driverNamesModalShown, setDriverNamesModalShown] = useState(false);
    const [driverNamesModalDriverIdx, setDriverNamesModalDriverIdx] = useState(0);

    const [carSelectorModalShown, setCarSelectorModalShown] = useState(false);
    const [carSelectorModalDriverIdx, setCarSelectorModalDriverIdx] = useState(0);

    const [numberOfDriversRacing, setNumberOfDriversRacing] = useState(0);

    // Using refs...
    //  see: https://stackoverflow.com/questions/57847594/react-hooks-accessing-up-to-date-state-from-within-a-callback
    //  Each of the following values which are "ref'd up" are used inside the processLaps callback.
    //    If we didn't use Refs (or some similar technique), then referring to the state
    //    variables would always return the initial value rather than the current value.


    const [hasRaceStarted, setHasRaceStarted] = useState(false);
    const hasRaceStartedRef = useRef();
    hasRaceStartedRef.current = hasRaceStarted;

    const [raceType, setRaceType] = useState(null);
    const raceTypeRef = useRef();
    raceTypeRef.current = raceType;


    const racePausedRef = useRef();
    racePausedRef.current = false;

    const [underStartersOrders, setUnderStartersOrders] = useState(false);
    
    const storeMqttHost = (newMqttHost) => {
        setConfig({...config, mqtthost: newMqttHost});
        localStorage.setItem("config", config);
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

    //setup localstorage defaults
    resetExpiredFastestLapToday();


    //used internally by processLaps
    const lapDataDefault = [
        {totalLaps: -1, lastLapTime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.999 },
        {totalLaps: -1, lastLapTime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.999 },
        {totalLaps: -1, lastLapTime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.999 },
        {totalLaps: -1, lastLapTime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.999 },
        {totalLaps: -1, lastLapTime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.999 },
        {totalLaps: -1, lastLapTime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.999 }
    ];
    const [lapData, setLapData] = useState([...lapDataDefault]);
    const lapDataRef = useRef();
    lapDataRef.current = lapData;


    //The viewmodel
    const lapsPerRace = raceTypeRef.current?.details.laps ?? 0;

    const driverDataDefault = {
        number: 99, 
        name: 'Driver X', 
        lastLap: '', 
        fastestLap: '', 
        isRaceFastestLap: false, 
        lapsRemaining: lapsPerRace, 
        p1LapsRemaining: lapsPerRace, 
        lapsCompleted: -1, 
        totalRaceTime: 0, 
        position: 0, 
        finished: false, 
        suspended: false,
        hasStartedRacing: false
    }

    let initialDrivers = []
    if (localStorage.getItem("drivers") == null) {
        initialDrivers = [
            {...driverDataDefault, number: 1, name: 'Driver A'},
            {...driverDataDefault, number: 2, name: 'Driver B'},
            {...driverDataDefault, number: 3, name: 'Driver C'},
            {...driverDataDefault, number: 4, name: 'Driver D'},
            {...driverDataDefault, number: 5, name: 'Driver E'},
            {...driverDataDefault, number: 6, name: 'Driver F'}
        ];
    } else {
        initialDrivers = JSON.parse(localStorage.getItem("drivers"))
    }

    const [drivers, setDrivers] = useState(initialDrivers);
    const driversRef = useRef();
    driversRef.current = drivers;


    const saveDrivers = (drivers) => {
        setDrivers(drivers);
        localStorage.setItem("drivers", JSON.stringify(driversRef.current));
    }

    const openDriverNamesModal = (driverIdx) => {
        setDriverNamesModalDriverIdx(driverIdx);
        setDriverNamesModalShown(true);
    }

    const openCarSelectorModal = (driverIdx) => {
        setCarSelectorModalDriverIdx(driverIdx);
        setCarSelectorModalShown(true);
    }

    const handleStartCountdown = (raceTypeObj) => {
        resetRaceValues(raceTypeObj);
        setUnderStartersOrders(true);
    }

    const handleGoGoGo = () => {
        setHasRaceStarted(true);
        setUnderStartersOrders(false);
        racePausedRef.current = false;

        //ideally we'd set raceStartTime.current = wsMsg.time when the lights go out,
        //  but we don't have that time info which is obtained from the server side python.
        //  I don't want any more complexity in the server side code (at the moment)
        //  and I don't want to have to sync server and client times, so we stick
        //  with zoomroom's implementation, which is that the race timing doesn't start
        //  until the first car crosses the line.
    }

    const handleManualRaceEnd = () => {
        console.log("handleManualRaceEnd inside LapCounter");
        setHasRaceStarted(false);
    }    

    const handleRaceEnd = () => {
        setHasRaceStarted(false);
        racePausedRef.current = false;
    }

    const resetRaceValues = (raceTypeObj) => {
        //TODO: this is first place we should use localStorage.
        //  the goal is to resume a race in the event of browser refresh, so all driver info and race
        //  statuses need to be stored

        //console.log("LapCounter:resetRaceValues"), raceTypeObj;
        setLapData([...lapDataDefault]);

        const newDrivers = [];
        for (const driver of drivers) {
            newDrivers.push({...driver, 
                lastLap: '', 
                fastestLap: '', 
                isRaceFastestLap: false,
                lapsRemaining: raceTypeObj.details.laps, 
                p1LapsRemaining: raceTypeObj.details.laps,
                lapsCompleted: -1,
                totalRaceTime: null, 
                position: null,
                finished: false,
                suspended: false,
                hasStartedRacing: false
            });
        }
        setDrivers(newDrivers);
        setRaceType(raceTypeObj);
        setHasRaceStarted(false);
        setNumberOfDriversRacing(0);
        racePausedRef.current = false;

        setRace(defaultRace);
    }


    //This is a callback from Mqtt, so like a setInterval, it lives outside of the React lifecycle
    //  Hence we need to use useRef to access the current state values
    const processLapMsg = (lapMsg) => {
        //console.log("INCOMING LAP DATA: ", lapMsg)
        if (!hasRaceStartedRef.current || racePausedRef.current) { return }
        
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

        

        console.log('=-=-=-=- newLap, newRace -=-=-=-=');
        console.dir(newLap);
        console.dir(newRace);

        //Fastest lap of this race
        console.log(`newLap.bestLapTime: ${newLap.bestLapTime} :::: Number(newRace.fastestLap): ${Number(newRace.fastestLap)}`);
        if (newLap.bestLapTime < Number(newRace.fastestLap)) {
            newRace = {...newRace, fastestLap: newLap.bestLapTime.toFixed(3)};
        }

        setRace(newRace);

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
                raceTypeRef.current.details.laps, 
                //statsRef.current.fastestLapToday,
                newRace.fastestLap,
                newRace.startTime        //Feels like this shouldn't be needed. All calcs that might need this should have been done??
        );

        console.log('modifiedDrivers');
        console.dir(modifiedDrivers);
        saveDrivers(modifiedDrivers);

        const numberOfDriversRacing = modifiedDrivers.reduce((acc, driver) => {
            return acc + Number(driver.hasStartedRacing);
        }, 0);
        console.log(`Number of Drivers Racing: ${numberOfDriversRacing}`);
        setNumberOfDriversRacing(numberOfDriversRacing);

        checkEndOfRace(modifiedDrivers, handleRaceEnd);
    }

    const handleRaceTypeChange = (raceTypeObj) => {
        console.log("LapCounter:handleRaceTypeChange", raceTypeObj);
        setRaceType(raceTypeObj);
    }

    const numberOfDriversRacingClassName = `numberOfDriversRacing${numberOfDriversRacing}`; 
    
    return (
        <div id="top">

            <div id={'lapcounter'}>
                <MqttSubscriber mqttHost={config.mqtthost} onIncomingLapMessage={processLapMsg} debug={DEBUG} />
                <Header
                    mqttHost={config.mqtthost}
                    setMqtthost={storeMqttHost}
                    onRaceTypeChange={handleRaceTypeChange}
                    onStartCountdown={handleStartCountdown}
                    onGoGoGo={handleGoGoGo}

                    fastestLapToday={statsRef.current.fastestLapToday}
                    hasRaceStarted={hasRaceStarted}
                    onRaceEnd={handleManualRaceEnd}
                    yellowFlagAdvantageDuration = {3.8}
                    onYellowFlagCountdown={() => { console.log('Lapcounter: Yellow Flag Countdown')}}
                    onYellowFlag={() => {racePausedRef.current = true;}}
                    onEndYellowFlag={() => {racePausedRef.current = false;}}
                    resetFastestLapToday = {resetFastestLapToday}
                />
                <div id="driverCardOuter">
                    <div id="driverCardContainer" className={numberOfDriversRacingClassName}>
                        <DriverCard driver={drivers[0]} underStartersOrders={underStartersOrders} onRequestOpenDriverNames={() => {openDriverNamesModal(0)}} onRequestOpenCarSelector={() => {openCarSelectorModal(0)}} />
                        <DriverCard driver={drivers[1]} underStartersOrders={underStartersOrders} onRequestOpenDriverNames={() => {openDriverNamesModal(1)}} onRequestOpenCarSelector={() => {openCarSelectorModal(1)}} />
                        <DriverCard driver={drivers[2]} underStartersOrders={underStartersOrders} onRequestOpenDriverNames={() => {openDriverNamesModal(2)}} onRequestOpenCarSelector={() => {openCarSelectorModal(2)}} />
                        <DriverCard driver={drivers[3]} underStartersOrders={underStartersOrders} onRequestOpenDriverNames={() => {openDriverNamesModal(3)}} onRequestOpenCarSelector={() => {openCarSelectorModal(3)}} />
                        <DriverCard driver={drivers[4]} underStartersOrders={underStartersOrders} onRequestOpenDriverNames={() => {openDriverNamesModal(4)}} onRequestOpenCarSelector={() => {openCarSelectorModal(4)}} />
                        <DriverCard driver={drivers[5]} underStartersOrders={underStartersOrders} onRequestOpenDriverNames={() => {openDriverNamesModal(5)}} onRequestOpenCarSelector={() => {openCarSelectorModal(5)}} />
                    </div>
                </div>
            </div>
           
           <EditDriverNamesModal 
                showMe={driverNamesModalShown}
                onClose={() => setDriverNamesModalShown(false)}
                drivers={drivers}
                setDrivers={(d) => saveDrivers(d)} 
                driverIdxToFocus={driverNamesModalDriverIdx} 
            />

            <CarSelectorModal 
                showMe={carSelectorModalShown}
                onClose={() => setCarSelectorModalShown(false)}
                carImgListUrl={config.apihost + '/api/cars'}
                drivers={drivers}
                setDrivers={(d) => saveDrivers(d)} 
                driverIdxToFocus={carSelectorModalDriverIdx} 
            />        
       
        </div>
    );
}


export default LapCounter;