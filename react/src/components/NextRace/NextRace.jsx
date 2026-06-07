import './NextRace.css';
import { useState } from 'react';
import { useLoaderData } from 'react-router-dom';
import CarSelectorModal from '../LapCounter/CarSelectorModal';


function NextRace() {
    const next_race_setup = useLoaderData();
    const [laneAssignments, setLaneAssignments] = useState(next_race_setup.lane_assignments);
    const [otherDrivers, setOtherDrivers] = useState(next_race_setup.other_drivers);
    const [carSelectorLane, setCarSelectorLane] = useState(null);

    const carMediaBase = `${import.meta.env.VITE_API_URL}/${import.meta.env.VITE_CAR_MEDIA_FOLDER}`;
    const defaultCarImg = `${carMediaBase}/GT_AA_Generic.jpg`;
    const carImageUrl = (picture) => picture ? `${carMediaBase}/${picture}` : defaultCarImg;

    const handleLaneToggle = async (laneNumber, enabled) => {
        const res = await fetch(`${import.meta.env.VITE_API_URL}/lanes/${laneNumber}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled }),
        });
        if (!res.ok) return;
        const data = await res.json();
        setLaneAssignments(data.lane_assignments);
        setOtherDrivers(data.other_drivers);
    };

    const hasFreeSlot = laneAssignments.some(a => a.id === 0 && a.lane_enabled);

    const handleRemoveDriver = async (laneNumber) => {
        const res = await fetch(`${import.meta.env.VITE_API_URL}/races/pending/lanes/${laneNumber}`, {
            method: 'DELETE',
        });
        if (!res.ok) return;
        const data = await res.json();
        setLaneAssignments(data.lane_assignments);
        setOtherDrivers(data.other_drivers);
    };

    const handleAddDriver = async (driverId) => {
        const res = await fetch(`${import.meta.env.VITE_API_URL}/races/pending/drivers`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ driver_id: driverId }),
        });
        if (!res.ok) return;
        const data = await res.json();
        setLaneAssignments(data.lane_assignments);
        setOtherDrivers(data.other_drivers);
    };

    const handleCarSelected = async (car) => {
        const res = await fetch(`${import.meta.env.VITE_API_URL}/races/pending/lanes/${carSelectorLane}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ car_id: car.id }),
        });
        if (!res.ok) return;
        const data = await res.json();
        setLaneAssignments(data.lane_assignments);
        setOtherDrivers(data.other_drivers);
        setCarSelectorLane(null);
    };

    return (
        <div id="nextrace-page">
            <div className="nr-columns">

                <div className="nr-col nr-col-assigned">
                    <h1>Next Race #{next_race_setup.race_number}</h1>
                    <table className="nr-table">
                        <thead>
                            <tr>
                                <th className="col-toggle">Lane</th>
                                <th className="col-car">Car</th>
                                <th className="col-name">Driver</th>
                                <th className="col-raced">Raced</th>
                                <th className="col-action"></th>
                            </tr>
                        </thead>
                        <tbody>
                        {laneAssignments.map(driver => (
                            <tr key={driver.lane_number} className={`lane-color-${driver.lane_color}`}>
                                <td className="col-toggle">
                                    <label className="lane-toggle">
                                        <input
                                            type="checkbox"
                                            role="switch"
                                            checked={driver.lane_enabled}
                                            onChange={(e) => handleLaneToggle(driver.lane_number, e.target.checked)}
                                        />
                                        <span className="toggle-track" />
                                    </label>
                                </td>
                                <td className="col-car">
                                    {driver.id > 0 && (
                                        <img
                                            src={carImageUrl(driver.car_picture)}
                                            alt="Car"
                                            className="car-thumbnail"
                                            onClick={() => setCarSelectorLane(driver.lane_number)}
                                            onError={(e) => { e.target.onerror = null; e.target.src = defaultCarImg; }}
                                        />
                                    )}
                                </td>
                                <td className="col-name">{driver.driver_name}</td>
                                <td className="col-raced">{driver.completed_races}</td>
                                <td className="col-action">
                                    <button
                                        className="nr-btn nr-btn-remove"
                                        aria-label="Remove driver"
                                        disabled={driver.id === 0}
                                        onClick={() => handleRemoveDriver(driver.lane_number)}
                                    >
                                        ×
                                    </button>
                                </td>
                            </tr>
                        ))}
                        </tbody>
                    </table>
                </div>

                <div className="nr-col nr-col-others">
                    <h1>Other Drivers</h1>
                    <div className="others-scroll">
                        <table className="nr-table">
                            <thead>
                                <tr>
                                    <th className="col-name">Driver</th>
                                    <th className="col-raced">Raced</th>
                                    <th className="col-action">Add</th>
                                </tr>
                            </thead>
                            <tbody>
                            {otherDrivers.map(driver => (
                                <tr key={driver.id}>
                                    <td className="col-name">{driver.driver_name}</td>
                                    <td className="col-raced">{driver.completed_races}</td>
                                    <td className="col-action">
                                        <button
                                            className="nr-btn nr-btn-add"
                                            aria-label="Add driver"
                                            disabled={!hasFreeSlot}
                                            onClick={() => handleAddDriver(driver.id)}
                                        >
                                            +
                                        </button>
                                    </td>
                                </tr>
                            ))}
                            </tbody>
                        </table>
                    </div>
                </div>

            </div>

            <CarSelectorModal
                showMe={carSelectorLane !== null}
                onClose={() => setCarSelectorLane(null)}
                carImgListUrl={`${import.meta.env.VITE_API_URL}/api/cars`}
                onCarSelected={handleCarSelected}
            />
        </div>
    );
}

export default NextRace;
