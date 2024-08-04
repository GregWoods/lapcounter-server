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
        type: defaultConfig.racepresets[0],
        hasStarted: false,
        underStartersOrders: false,
        firstCarCrossedStart: false,    //AKA: has race timing started
        startTime: null,
        paused: false,
        fastestLap: 99.999,
        numberOfDriversRacing: 0
    };

    // Using refs...
    //  see: https://stackoverflow.com/questions/57847594/react-hooks-accessing-up-to-date-state-from-within-a-callback
    //  Each of the following values which are "ref'd up" are used inside the processLaps callback.
    //    If we didn't use Refs (or some similar technique), then referring to the state
    //    variables would always return the initial value rather than the current value.

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

    //used internally by processLaps
    const lapDataDefault = [
        {totalLaps: -1, lastLapTime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.999 },
        {totalLaps: -1, lastLapTime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.999 },
        {totalLaps: -1, lastLapTime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.999 },
        {totalLaps: -1, lastLapTime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.999 },
        {totalLaps: -1, lastLapTime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.999 },
        {totalLaps: -1, lastLapTime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.999 }
    ];
    const [lapData, setLapData] = useLocalStorageState('lap', {defaultValue: [...lapDataDefault]});
    const lapDataRef = useRef();
    lapDataRef.current = lapData;


    //The drivers viewmodel
    //  Not all properties are set in the default, since we do not want to overwrite things like "name", "carImgUrl", even for a new race
    const lapsPerRace = raceRef.current.RaceType?.details.laps ?? 0;
    const driverDataDefault = {
        lastLap: '', 
        fastestLap: '', 
        isRaceFastestLap: false, 
        lapsRemaining: lapsPerRace, 
        p1LapsRemaining: lapsPerRace, 
        lapsCompleted: -1, 
        totalRaceTime: null, 
        position: null, 
        finished: false, 
        suspended: false,
        hasStartedRacing: false,
        //carImgUrl: null,
        spotlightMe: false
    };
    const initialDrivers = [
        {...driverDataDefault, number: 1, name: 'Driver A'},
        {...driverDataDefault, number: 2, name: 'Driver B'},
        {...driverDataDefault, number: 3, name: 'Driver C'},
        {...driverDataDefault, number: 4, name: 'Driver D'},
        {...driverDataDefault, number: 5, name: 'Driver E'},
        {...driverDataDefault, number: 6, name: 'Driver F'}
    ];
    const [drivers, setDrivers] = useLocalStorageState('drivers', {defaultValue: [...initialDrivers]});
    const driversRef = useRef();
    driversRef.current = drivers;


    //Normal state variables for simple, non persistent state, such as dialog open state
    const [driverNamesModalShown, setDriverNamesModalShown] = useState(false);
    const [driverNamesModalDriverIdx, setDriverNamesModalDriverIdx] = useState(0);

    const [carSelectorModalShown, setCarSelectorModalShown] = useState(false);
    const [carSelectorModalDriverIdx, setCarSelectorModalDriverIdx] = useState(0);



    const storeMqttHost = (newMqttHost) => {
        setConfig({...config, mqtthost: newMqttHost});
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
                ...driverDataDefault, 
                lapsRemaining: raceTypeObj.details.laps, 
                p1LapsRemaining: raceTypeObj.details.laps
            });
        }
        setDrivers(newDrivers);
    }

    const openCarSelectorModal = (driverIdx) => {
        setCarSelectorModalDriverIdx(driverIdx);
        setCarSelectorModalShown(true);
        //
        unhideDrivers();
        //setSpotlightMe(driverIdx) is run inside modal component
    }

    const [tmpNumberOfDriversRacing, setTmpNumberOfDriversRacing] = useState();
    const [unstartedDrivers, setUnstartedDrivers] = useState([]);

    const unhideDrivers = () => {
        //unhides drivers who have not started racing. Used when changing the car images. 
        //  Allows for additional drivers joining the race later, with correct CarImg shown

        //Adjust the left side of the DriverCards container element, which fake-centers the driverCards
        setTmpNumberOfDriversRacing(race.numberOfDriversRacing);
        setRace({...race, numberOfDriversRacing: 6});

        //store driver.number of any driver who hasn't started racing (ie. they are currently hidden)
        //  then unhide them
        const tmpUnstartedDrivers = drivers.filter(drv => !drv.hasStartedRacing).map(drv => drv.number);
        setUnstartedDrivers(tmpUnstartedDrivers);
        console.log(`tmpUnstartedDrivers: ${tmpUnstartedDrivers}`);

        //while the car image dialog is open, set all drivers' .hasStartedRacing to true, so they become visible
        const updatedDrivers = drivers.map(drv => ({ ...drv, hasStartedRacing: true }));
        setDrivers(updatedDrivers);
    }

    const rehideDrivers = () => {
        setRace({...race, numberOfDriversRacing: tmpNumberOfDriversRacing});

        //using the saved list of drivers who have not started racing, rehide them
        const tmpDrivers = [...drivers].map((driver, index) => {
            driver.spotlightMe = false;
            driver.hasStartedRacing = unstartedDrivers.indexOf(driver.number) === -1;
            console.log(`${index} ${driver.name} hasStartedRacing: ${driver.hasStartedRacing} spotlightMe: ${driver.spotlightMe}`);
            return driver;
        });
        setDrivers(tmpDrivers);
    }

    const closeCarSelectorModal = () => {
        setCarSelectorModalShown(false);
        rehideDrivers();
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

        

        console.log('=-=-=-=- newLap, newRace -=-=-=-=');
        console.dir(newLap);
        console.dir(newRace);

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
                <MqttSubscriber mqttHost={config.mqtthost} onIncomingLapMessage={processLapMsg} debug={DEBUG} />
                <Header
                    mqttHost={config.mqtthost}
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
                            carImgListUrl={config.apihost + '/api/cars'}
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