const DEBUG = false;
const suspendAfter = 12.0;

export const modifyDriversViewModel = (drivers, idx, lapData, targetLaps, raceFastestLap, absoluteRaceStartTime)  => {

    var newDrivers = [...drivers];

    if (drivers[idx].finished) {
        console.log("===== This drive has FINISHED ======");
        //do nothing
        return newDrivers;
    }

    //only one "row" of lapData changed. 
    //  we now change the equivalent row in "drivers" to force a re-render
    const driverInfo = {
        ...drivers[idx],
        "number": idx+1, 
        //"lastLap": lapData.lastLapTime > 0 ? lapData.lastLapTime.toFixed(3) : '', 
        //I prefer to see something appear (even if it is 0.000) when the driver crosses the line on the start of lap 1
        "lastLap":lapData.lastLapTime.toFixed(3), 
        "fastestLap": lapData.bestLapTime < 999 ? lapData.bestLapTime.toFixed(3) : '',
        "lapsRemaining": (lapData.totalLaps < targetLaps) ? targetLaps - lapData.totalLaps : 0,
        "lapsCompleted": lapData.totalLaps,
        "totalRaceTime": (lapData.absoluteRaceTime - absoluteRaceStartTime).toFixed(3),
        "hasStartedRacing": true
    }
    //if (driverInfo.raceFastestLap) console.log("New Fastest Lap: " + driverInfo.fastestLap);

    //if any driver has zero laps remaining, then the chequered flag has dropped. This was your last lap
    if (driverInfo.lapsRemaining === 0 || newDrivers.some(d => d.lapsRemaining === 0)) {
        driverInfo.finished = true;
    }

    //amend one row
    newDrivers[idx] = driverInfo

    //amend position info for all drivers... by sorting the array
    newDrivers.sort(driverSorter);
    const p1LapsRemaining = newDrivers[0].lapsRemaining;

    //get latest absoluteRaceTime
    const latestRaceTime = Math.max.apply(null, drivers.map(function(drv) { return drv.totalRaceTime; }))

    //Do stuff which applies to all drivers at once, like determining position
    newDrivers.forEach((driver, idx) => { 
        driver.position = idx+1; 
        driver.p1LapsRemaining = p1LapsRemaining;
        driver.isRaceFastestLap = !isNaN(parseFloat(driver.fastestLap)) && parseFloat(driver.fastestLap) == parseFloat(raceFastestLap);

        //suspend a driver who hasn't posted a lap in 'suspendAfter' seconds
        driver.suspended = (parseInt(driver.totalRaceTime) + suspendAfter) < latestRaceTime;
    });
    //now re-sort by driver number, so we have the original ordering.
    //  any visual reordering will be done with css "order"
    newDrivers.sort((a, b) => a.number - b.number);
    if (DEBUG) {console.log("sorted newDrivers: ", newDrivers)}

    //save back to drivers
    //  instead of creating a ref to drivers so we have the updated value, I could have 
    //     used the 2nd param (a function) of setDrivers

    return newDrivers;
}



//this method processes laps without regard for the state of the race
export const processMessage = (newLapMsg, driverLapData, firstCarCrossedStart, setFirstCarCrossedStart, 
    raceStartTimeRef, fastestLap, setFastestLap) => {

    driverLapData.totalLaps += 1;
    driverLapData.absoluteRaceTime = newLapMsg.time;

    if (DEBUG) { console.log("Total laps for driver: ", driverLapData.totalLaps); }

    var tempCalcLapTime;
    var lastMsgTime;

    if (!firstCarCrossedStart) {
        //Nobody had crossed the start until now. This guy starts all the race timing
        setFirstCarCrossedStart(true);

        raceStartTimeRef.current = newLapMsg.time;

        console.log("AAAA First car has crossed line,  ID=[" + newLapMsg.car + "].    Race timer starts now"); 
        console.log("AAAA race start time: " + newLapMsg.time);

        //this is just to indicate in the UI they crossed the line for the first time after lights out
        driverLapData.lastLapTime = 0.00;

        //the first driver to cross the line still needs their lastMessageTime setting, just like everyone else on their lap 0
        driverLapData.lastMessageTime = newLapMsg.time;
        return driverLapData;
    } 
    
    //every other crossing of the line goes here
    
    //yes, there is duplication in these conditions. I stand by it, as it helps keep the logic clear

    //"Lap 0" is not lap. It is the time they crossed the line after starting from the grid
    if (driverLapData.totalLaps == 0) {
        //this is lap0 for everyone except the very first car to cross the line (we already handled him, above)
        console.log("BBBB  totalLaps=0, ID: " + newLapMsg.car + " raceStartTime: " + raceStartTimeRef.current);
        console.log("BBBB Lap 0 offset to lead driver: " + (newLapMsg.time - raceStartTimeRef.current));
        //this is just to indicate in the UI they crossed the line for the first time after lights out
        // we don't any lap time calculations for this "lap"
        driverLapData.lastLapTime = 0.00; 
        driverLapData.lastMessageTime = newLapMsg.time;
        return driverLapData;
    } 
    
    if (driverLapData.totalLaps == 1) {
        //lap 1
        //Special case, first countable lap for this driver, we time our lap from the time point the 
        //  very first driver crossed the line (our pseudo race start)
        lastMsgTime = raceStartTimeRef.current;
        console.log("CCCC  totalLaps=1, ID: " + newLapMsg.car + " raceStartTime: " + raceStartTimeRef.current);

    } else if (driverLapData.totalLaps > 1) {
        lastMsgTime = driverLapData.lastMessageTime
        console.log("DDDD  totalLaps>1, ID: " + newLapMsg.car + " lastMessageTime: " + lastMsgTime);
    }

    //Calculate lap times
    console.log("r.time: " + newLapMsg.time + "    | lastMsgTime: " + lastMsgTime);
    tempCalcLapTime = newLapMsg.time - lastMsgTime;
    driverLapData.lastLapTime = tempCalcLapTime;

    //Calc driver best lap time
    if (tempCalcLapTime < driverLapData.bestLapTime) {
        driverLapData.bestLapTime = tempCalcLapTime;
    }

    //this function has too many side effects. it modified the return values and sets other global properties. 
    // this whole area needs refactoring

    //set new fastest lap
    if (fastestLap !== null) {
        if (tempCalcLapTime < Number(fastestLap)) {
            setFastestLap(tempCalcLapTime.toFixed(3));
        }
    } else {
        //no fastest lap has been set... so this lap is now fastest
        setFastestLap(tempCalcLapTime.toFixed(3));
    }
    driverLapData.lastMessageTime = newLapMsg.time;
    return driverLapData;
}



export const checkEndOfRace = (driversData, handleRaceEnd) => {
    //if at least one person has finished
    if (driversData.some(d => d.finished)) {    
        //and any remaining haven't even set off (totalRaceTime > 0), then the race is over
        if (driversData.every(d => (d.finished || d.totalRaceTime < 0.1))) {
            handleRaceEnd();
        }
    }
}


const driverSorter = (driverA, driverB) => {
    //order by lapsCompleted asc
    if (driverA.lapsCompleted > driverB.lapsCompleted) {
        return -1;
    }    
    if (driverA.lapsCompleted < driverB.lapsCompleted) {
        return 1;
    }

    //when laps are the same, order by totalRaceTime desc
    const raceTimeA = parseFloat(driverA.totalRaceTime);
    const raceTimeB = parseFloat(driverB.totalRaceTime);
    if (raceTimeA > raceTimeB) {
        return 1;
    }       
    if (raceTimeA < raceTimeB) {
        return -1;
    }

    return 0;
}