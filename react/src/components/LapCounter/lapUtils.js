// Race logic used to live here (calculateLapTime, modifyDriversViewModel,
// checkEndOfRace) before that moved server-side into lapdata's race manager, which
// publishes race_state for React to render directly. driverSorter is what's left — a
// plain comparator with no race logic of its own, still used by CarSelectorModal.

export const driverSorter = (driverA, driverB) => {
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
