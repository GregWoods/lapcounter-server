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
    //We could also have used array.map and altered all the rows of drivers
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

        //suspend a driver who hasn't posted a lap in X seconds
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


//wsMsg, oldLap, firstCarCrossedStartRef.current, setFirstCarCrossedStart, 
//            setRaceStartTime, raceFastestLapRef.current, setRaceFastestLap, lapRecordRef.current, setFastestLap

//this method processes laps without regard for the state of the race
export const processMessage = (r, thisLap, firstCarCrossedStart, setFirstCarCrossedStart, 
    raceStartTime, setRaceStartTime, fastestLap, setFastestLap) => {

    thisLap.totalLaps += 1;
    thisLap.absoluteRaceTime = r.time;

    if (DEBUG) { console.log("Total laps for driver: ", thisLap.totalLaps); }

    var tempCalcLapTime;
    var lastMsgTime;

    if (!firstCarCrossedStart) {
        //Nobody had crossed the start until now. This guy starts all the race timing
        setFirstCarCrossedStart(true);

        setRaceStartTime(r.time);

        console.log("AAAA First car has crossed line,  ID=[" + r.car + "].    Race timer starts now"); 
        console.log("AAAA race start time: " + r.time);

        //this is just to indicate in the UI they crossed the line for the first time after lights out
        thisLap.lastLapTime = 0.00;

        //the first driver to cross the line still needs their lastMessageTime setting, just like everyone else on their lap 0
        thisLap.lastMessageTime = r.time;
        return thisLap;     
    } 
    
    //every other crossing of the line goes here
    
    //yes, there is duplication in these conditions. I stand by it, as it helps keep the logic clear

    //"Lap 0" is not lap. It is the time they crossed the line after starting from the grid
    if (thisLap.totalLaps == 0) {
        //this is lap0 for everyone except the very first car to cross the line (we already handled him, above)
        console.log("BBBB  totalLaps=0, ID: " + r.car + " raceStartTime: " + raceStartTime);
        console.log("BBBB Lap 0 offset to lead driver: " + (r.time - raceStartTime));
        //this is just to indicate in the UI they crossed the line for the first time after lights out
        // we don't any lap time calculations for this "lap"
        thisLap.lastLapTime = 0.00; 
        thisLap.lastMessageTime = r.time;
        return thisLap;
    } 
    
    if (thisLap.totalLaps == 1) {
        //lap 1
        //Special case, first countable lap for this driver, we time our lap from the time point the very first driver crossed the line (our pseudo race start)
        lastMsgTime = raceStartTime;
        console.log("CCCC  totalLaps=1, ID: " + r.car + " raceStartTime: " + raceStartTime);

    } else if (thisLap.totalLaps > 1) {
        lastMsgTime = thisLap.lastMessageTime
        console.log("DDDD  totalLaps>1, ID: " + r.car + " lastMessageTime: " + lastMsgTime);     
    }

    //Calculate lap times
    console.log("r.time: " + r.time + "    | lastMsgTime: " + lastMsgTime);
    tempCalcLapTime = r.time - lastMsgTime;
    thisLap.lastLapTime = tempCalcLapTime;

    //Calc driver best lap time
    if (tempCalcLapTime < thisLap.bestLapTime) {
        thisLap.bestLapTime = tempCalcLapTime;
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
    thisLap.lastMessageTime = r.time;
    return thisLap;
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