import './NextRace.css';
import { useLoaderData } from 'react-router-dom';

function NextRace() {
    const drivers = useLoaderData();

    return (
        <div className="next-race-container">
            <h1>Next Race</h1>

            <div className="drivers-grid">
                {drivers.map(driver => (
                    <div key={driver.id} className="driver-card">
                        <h2>{driver.first_name} {driver.last_name}</h2>
                        <div className="driver-stats">
                            <p>Completed races: {driver.completed_races}</p>
                            <p>Lane assignments:</p>
                            <div className="lane-stats">
                                <span>Lane 1: {driver.lane1_count}</span>
                                <span>Lane 2: {driver.lane2_count}</span>
                                <span>Lane 3: {driver.lane3_count}</span>
                                <span>Lane 4: {driver.lane4_count}</span>
                                <span>Lane 5: {driver.lane5_count}</span>
                                <span>Lane 6: {driver.lane6_count}</span>
                            </div>
                            {driver.sit_out_next_race && (
                                <p className="sit-out-warning">⚠️ Sitting out next race</p>
                            )}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

export default NextRace;