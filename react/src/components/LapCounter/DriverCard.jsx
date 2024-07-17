import DriverCardPosition from './DriverCardPosition';
import './DriverCard.css';
import './DriverColors.css';
import DriverCardTime from './DriverCardTime';


const DriverCard = ({driver, underStartersOrders, onRequestOpenDriverNames, onRequestOpenCarSelector}) => {
    let className = 'drivercard driver' + driver.number;
    if (!underStartersOrders && driver.lapsCompleted > -1) {
        //if (driver.suspended) {
        //    className += ' suspended';
        //} else {
            className += ' show';
        //}
    }

    const fastestLapClass = (driver.isRaceFastestLap) ? "fastestlaptime raceFastestLap" : "fastestlaptime personalFastestLap";


    const driverPosition = driver.position;


    let lastLapClass = "lastlaptime";
    if  (driver.lastLap == driver.fastestLap) {
        if (driver.isRaceFastestLap) {
            lastLapClass += " raceFastestLap"
        } else {
            lastLapClass += " personalFastestLap"
        }
    }



    return (
        <div className={className} data-order={driverPosition}>

            <div className="drivername emphasized" onClick={onRequestOpenDriverNames}>
                <div>{driver.name}</div>
            </div>
            <div className="carimg" onClick={onRequestOpenCarSelector}>
                <img alt="FSR Logo" src="../../images/cars/car0.png" />
            </div>

            <div className="drivercontent">
                <DriverCardTime fastestLapClass={lastLapClass} label="Last Lap" lapTime={driver.lastLap} />
                <DriverCardTime fastestLapClass={fastestLapClass} label="Fastest Lap" lapTime={driver.fastestLap} />
            </div>

            <DriverCardPosition 
                finished={driver.finished} 
                lapsRemaining={driver.lapsRemaining}
                p1LapsRemaining={driver.p1LapsRemaining}
                lapsCompleted={driver.lapsCompleted}
                position={driver.position} 
                totalRaceTime={driver.totalRaceTime} />
 
        </div>
    );
}

export default DriverCard;