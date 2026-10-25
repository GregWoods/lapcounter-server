/* eslint-disable no-unused-vars */
import './DriverCardPosition.css';


const DriverCardPosition = ({finished, lapsRemaining, p1LapsRemaining, lapsCompleted, position}) => {
    if (!finished) {
            return showInRacePositionInfo(position, lapsRemaining, p1LapsRemaining);
        } else {
            return showEndOfRacePositionInfo(position, lapsRemaining, lapsCompleted);
        }

}

const showInRacePositionInfo = (position, lapsRemaining, p1LapsRemaining) => {
    //const line1 = (lapsRemaining == p1LapsRemaining) ? "Laps Remaining" : "+" + (lapsRemaining - p1LapsRemaining) + " laps";
    const line1 = "Laps Remaining";
    //const line2 = (lapsRemaining == p1LapsRemaining) ? lapsRemaining : "+" + (lapsRemaining - p1LapsRemaining);
    const line2 = lapsRemaining;
    return (
        <div className="lapsremaining emphasized">
            <div className="timelbl">{line1}</div>
            <div className="laps">{line2}</div>
        </div>
    );        
}

const showEndOfRacePositionInfo = (position, lapsRemaining, lapsCompleted) => {
    //const laps = (lapsRemaining > 0) ? "-" + lapsRemaining + " laps " : lapsCompleted + " laps";
    // laps_completed is net of lap penalties and goes negative while a penalty is still
    // owed (#86). Floored here, for display only.
    const laps = Math.max(0, lapsCompleted) + " laps";
    return(
        <div className="lapsremaining emphasized">
            <div className="timelbl">{laps}</div>
            <div className="laps">P{position}</div>
        </div>
    );
}


export default DriverCardPosition;