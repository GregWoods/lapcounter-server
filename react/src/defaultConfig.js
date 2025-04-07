
export const defaultConfig = {
    // These defaults are based on the production docker setup
    // They are stored in localstorage
    circuitname: import.meta.env.VITE_CIRCUIT_NAME,
    mqtturl: import.meta.env.VITE_MQTT_URL,
    apiurl: import.meta.env.VITE_API_URL,
    carmediafolder: import.meta.env.VITE_CAR_MEDIA_FOLDER,
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

export const defaultRace = {
    type: defaultConfig.racepresets[0],
    hasStarted: false,
    underStartersOrders: false,
    firstCarCrossedStart: false,    //AKA: has race timing started
    startTime: null,
    paused: false,
    fastestLap: 99.999,
    numberOfDriversRacing: 6
};

    //used internally by processLaps
export const lapDataDefault = [
    {totalLaps: -1, lastLapTime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.999 },
    {totalLaps: -1, lastLapTime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.999 },
    {totalLaps: -1, lastLapTime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.999 },
    {totalLaps: -1, lastLapTime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.999 },
    {totalLaps: -1, lastLapTime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.999 },
    {totalLaps: -1, lastLapTime: 999.999, lastMessageTime: 0.000, bestLapTime: 999.999 }
];

//The drivers viewmodel
//  Not all properties are set in the default, since we do not want to overwrite things like "name", "carImgUrl", even for a new race
export const getDriverDataDefault = (lapsPerRace) => {
    return {
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
        spotlightMe: false
    }
};

export const getInitialDrivers = (lapsPerRace, defaultCarImg) => {
    const driverDataDefault = getDriverDataDefault(lapsPerRace);
    return [
        {...driverDataDefault, number: 1, name: 'Driver A', carImgUrl: defaultCarImg, hasStartedRacing: true, position: 1},
        {...driverDataDefault, number: 2, name: 'Driver B', carImgUrl: defaultCarImg, hasStartedRacing: true, position: 2},
        {...driverDataDefault, number: 3, name: 'Driver C', carImgUrl: defaultCarImg, hasStartedRacing: true, position: 3},
        {...driverDataDefault, number: 4, name: 'Driver D', carImgUrl: defaultCarImg, hasStartedRacing: true, position: 4},
        {...driverDataDefault, number: 5, name: 'Driver E', carImgUrl: defaultCarImg, hasStartedRacing: true, position: 5},
        {...driverDataDefault, number: 6, name: 'Driver F', carImgUrl: defaultCarImg, hasStartedRacing: true, position: 6}
    ];
};
