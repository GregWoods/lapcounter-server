import './LapCounter.css';
import useLocalStorageState from 'use-local-storage-state'
import MqttSubscriber from '../MqttSubscriber.jsx'
import EditDriverNamesModal from './EditDriverNamesModal.jsx';
import CarSelectorModal from './CarSelectorModal.jsx';
import DriverCard from './DriverCard.jsx';
import Header from './Header.jsx';
import { useState, useRef } from 'react';
import {modifyDriversViewModel, processMessage, checkEndOfRace} from './processLap.js';


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
    /*
    //developer defaults
    defaultConfig = {...defaultConfig,
        mqtthost: "ws://127.0.0.1:8080",
        apihost: "http://127.0.0.1:5001"
    };
    */

    //update localStorage config with default values if any are missing
    const [config, setConfig] = useLocalStorageState('config');
    if (!config) {
        setConfig(defaultConfig);
    } else {
        for (const key in defaultConfig) {
            if (!(key in config)) {
                config[key] = defaultConfig[key];
            }
        }
        setConfig(config);
    }

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
    const [firstCarCrossedStart, setFirstCarCrossedStart] = useState(false);
    const firstCarCrossedStartRef = useRef();
    firstCarCrossedStartRef.current = firstCarCrossedStart;

    const [fastestLapToday, setFastestLapToday] = useState(localStorage.getItem("config_fastestLapToday"));
    const fastestLapTodayRef = useRef();
    fastestLapTodayRef.current = fastestLapToday;

    const [hasRaceStarted, setHasRaceStarted] = useState(false);
    const hasRaceStartedRef = useRef();
    hasRaceStartedRef.current = hasRaceStarted;

    const raceStartTimeRef = useRef(0.00);

    const [raceType, setRaceType] = useState(null);
    const raceTypeRef = useRef();
    raceTypeRef.current = raceType;

    const [raceFastestLap, setRaceFastestLap] = useState(9999);
    const raceFastestLapRef = useRef();
    raceFastestLapRef.current = raceFastestLap;

    const racePausedRef = useRef();
    racePausedRef.current = false;

    const [underStartersOrders, setUnderStartersOrders] = useState(false);
    
    const storeMqttHost = (newMqttHost) => {
        setConfig({...config, mqtthost: newMqttHost});
        localStorage.setItem("config", config);
    }

    const storeFastestLapToday = (lapTime) => {
        localStorage.setItem("config_fastestLapToday", lapTime);
        localStorage.setItem("config_fastestLapTodayUpdatedOn", Date());
        setFastestLapToday(lapTime);
    }

    const resetTodaysFastestLap = () => {
        //  reset lap record if it is more than 24h old. Good enough!
        var fastestLapTodayUpdatedOn = new Date(localStorage.getItem("config_fastestLapTodayUpdatedOn")).getTime();
        var now = new Date();
        var twentyFourhoursAgo = now.setDate(now.getDate() - 1);

        if (fastestLapToday === '' || fastestLapToday === null || fastestLapTodayUpdatedOn < twentyFourhoursAgo) {
            forceResetFastestLap();
        }
    }

    const forceResetFastestLap = () => {
        storeFastestLapToday("99.999");
    }

    //setup localstorage defaults
    resetTodaysFastestLap();


    //used internally by processLaps
    const lapDataDefault = [
        {totalLaps: -1, lastlaptime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.99 },
        {totalLaps: -1, lastlaptime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.99 },
        {totalLaps: -1, lastlaptime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.99 },
        {totalLaps: -1, lastlaptime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.99 },
        {totalLaps: -1, lastlaptime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.99 },
        {totalLaps: -1, lastlaptime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.99 }
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

    var initialDrivers = []
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
        for (var driver of drivers) {
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
        setRaceFastestLap(9999);
        setFirstCarCrossedStart(false);
        setNumberOfDriversRacing(0);
        racePausedRef.current = false;
    }

    
    const processLap = (lapMsg) => {
        console.log("INCOMING LAP DATA: ", lapMsg)
        if (!hasRaceStartedRef.current || racePausedRef.current) { return }
        const carIdx = lapMsg.car - 1;
        const laps = lapDataRef.current
        const oldLap = laps[carIdx];
        
        //convert websocket message into useful lap data
        console.log("==ProcessMessage, car:" + lapMsg.car);

        const newLap = processMessage(lapMsg, oldLap, 
            firstCarCrossedStartRef.current, setFirstCarCrossedStart, 
            raceStartTimeRef, 
            fastestLapTodayRef.current, storeFastestLapToday);
        
        //Set Fastest Lap for this Race. Used to display purple lap time for a driver
        //  we do it here and not in processLapjs processMessage, because here, we only run it if the race is underway
        //console.log("RACE FASTEST LAP: " + newLap.bestLapTime + " : " + raceFastestLapRef.current + " : " + newLap.bestLapTime <= raceFastestLapRef.current);
        if (newLap.bestLapTime <= raceFastestLapRef.current) {
            setRaceFastestLap(newLap.bestLapTime.toFixed(3));
            //console.log("New fastest Lap: " + newLap.bestLapTime);
        }

        laps[carIdx] = newLap;
        setLapData(laps);

        console.log(`raceStartTimeRef.current: ${raceStartTimeRef.current}`)
        //create "drivers" view-model from lap data
        var modifiedDrivers = modifyDriversViewModel(
                driversRef.current, 
                carIdx, 
                newLap, 
                raceTypeRef.current.details.laps, 
                raceFastestLapRef.current, 
                raceStartTimeRef.current);

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
                <MqttSubscriber mqttHost={config.mqtthost} onIncomingLapMessage={processLap} debug={DEBUG} />
                <Header
                    mqttHost={config.mqtthost}
                    setMqtthost={storeMqttHost}
                    onRaceTypeChange={handleRaceTypeChange}
                    onStartCountdown={handleStartCountdown}
                    onGoGoGo={handleGoGoGo}

                    fastestLapToday={fastestLapToday}
                    hasRaceStarted={hasRaceStarted}
                    onRaceEnd={handleManualRaceEnd}
                    yellowFlagAdvantageDuration = {3.8}
                    onYellowFlagCountdown={() => { console.log('Lapcounter: Yellow Flag Countdown')}}
                    onYellowFlag={() => {racePausedRef.current = true;}}
                    onEndYellowFlag={() => {racePausedRef.current = false;}}
                    forceResetFastestLap = {forceResetFastestLap}
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