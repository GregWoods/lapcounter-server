import './NextRace.css';
import { useState, useRef } from 'react';
import { useLoaderData, Link } from 'react-router-dom';
import CarSelectorModal from '../LapCounter/CarSelectorModal';
import MqttSubscriber from '../MqttSubscriber';
import PageHeader from '../PageHeader/PageHeader';
import { API_URL, MQTT_URL, CAR_MEDIA_URL } from '../../endpoints.js';


function NextRace() {
    const next_race_setup = useLoaderData();

    if (next_race_setup?.error || !next_race_setup?.lane_assignments) {
        // With a session still in progress the queue is empty, not finished — say so, and
        // point at Race Control, which is where it gets regenerated.
        const sessionRunning = next_race_setup?.activeSessionId != null;
        return (
            <div id="nextrace-page">
                <PageHeader title="Next Race" />
                <div className="nr-empty">
                    <p>{sessionRunning ? 'No races queued for this session' : 'Session has ended'}</p>
                    {sessionRunning
                        ? <Link to="/racecontrol" className="nr-empty-link">Regenerate in Race Control</Link>
                        : <Link to="/results" className="nr-empty-link">View Results</Link>}
                </div>
            </div>
        );
    }

    return <NextRaceSetupView next_race_setup={next_race_setup} />;
}

function NextRaceSetupView({ next_race_setup }) {
    const [laneAssignments, setLaneAssignments] = useState(next_race_setup.lane_assignments);
    const [otherDrivers, setOtherDrivers] = useState(next_race_setup.other_drivers);
    const [carSelectorLane, setCarSelectorLane] = useState(null);

    const [raceNumber, setRaceNumber] = useState(next_race_setup.race_number);
    const [sessionNumber, setSessionNumber] = useState(next_race_setup.session_number ?? null);
    const [sessionRacesTotal, setSessionRacesTotal] = useState(next_race_setup.session_races_total ?? null);

    const refreshPendingRace = () => {
        fetch(`${API_URL}/races/pending/`)
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                if (data) {
                    setLaneAssignments(data.lane_assignments);
                    setOtherDrivers(data.other_drivers);
                    if (data.race_number) setRaceNumber(data.race_number);
                    if (data.session_number != null) setSessionNumber(data.session_number);
                    if (data.session_races_total != null) setSessionRacesTotal(data.session_races_total);
                }
            })
            .catch(() => {});
    };

    const handleRaceControl = (msg) => {
        if (msg.command === 'prepare') refreshPendingRace();
    };

    // Lineup edits go to the API only, so lapdata (and every display fed by its
    // race_state) would keep the lineup it staged. Ask it to re-read; lapdata ignores
    // this unless the staged race is still NotStarted.
    const mqttClientRef = useRef(null);
    const notifyLineupChanged = () => {
        mqttClientRef.current?.publish('race_control', JSON.stringify({ command: 'reload_lineup' }));
    };

    const lastRaceStateRef = useRef(null);
    const handleRaceState = (raceState) => {
        const prev = lastRaceStateRef.current;
        lastRaceStateRef.current = raceState.state;
        if (raceState.state !== prev && (raceState.state === 'Running' || raceState.state === 'Finished')) {
            refreshPendingRace();
        }
    };

    const carMediaBase = `${CAR_MEDIA_URL}`;
    const defaultCarImg = `${carMediaBase}/GT_AA_Generic.jpg`;
    const carImageUrl = (picture) => picture ? `${carMediaBase}/${picture}` : defaultCarImg;

    const handleLaneToggle = async (laneNumber, enabled) => {
        const res = await fetch(`${API_URL}/lanes/${laneNumber}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled }),
        });
        if (!res.ok) return;
        const data = await res.json();
        setLaneAssignments(data.lane_assignments);
        setOtherDrivers(data.other_drivers);
        notifyLineupChanged();
    };

    const hasFreeSlot = laneAssignments.some(a => a.id === 0 && a.lane_enabled);

    const handleRemoveDriver = async (laneNumber) => {
        const res = await fetch(`${API_URL}/races/pending/lanes/${laneNumber}`, {
            method: 'DELETE',
        });
        if (!res.ok) return;
        const data = await res.json();
        setLaneAssignments(data.lane_assignments);
        setOtherDrivers(data.other_drivers);
        notifyLineupChanged();
    };

    const handleAddDriver = async (driverId) => {
        const res = await fetch(`${API_URL}/races/pending/drivers`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ driver_id: driverId }),
        });
        if (!res.ok) return;
        const data = await res.json();
        setLaneAssignments(data.lane_assignments);
        setOtherDrivers(data.other_drivers);
        notifyLineupChanged();
    };

    const handleCarSelected = async (car) => {
        const res = await fetch(`${API_URL}/races/pending/lanes/${carSelectorLane}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ car_id: car.id }),
        });
        if (!res.ok) return;
        const data = await res.json();
        setLaneAssignments(data.lane_assignments);
        setOtherDrivers(data.other_drivers);
        notifyLineupChanged();
        setCarSelectorLane(null);
    };

    return (
        <div id="nextrace-page">
            <MqttSubscriber
                mqttHost={MQTT_URL}
                onRaceStateMessage={handleRaceState}
                onRaceControlMessage={handleRaceControl}
                clientRef={mqttClientRef}
            />
            <PageHeader title={`Next - ${sessionNumber != null ? `Session ${sessionNumber}, ` : ''}Race ${raceNumber}${sessionRacesTotal != null ? ` of ${sessionRacesTotal}` : ''}`} />
            <div className="nr-columns">

                <div className="nr-col nr-col-assigned">
                    <table className="nr-table">
                        <thead>
                            <tr>
                                <th className="col-toggle">Lane</th>
                                <th className="col-car">Car</th>
                                <th className="col-name">Driver</th>
                                <th className="col-raced">Raced</th>
                                <th className="col-action">Sit Out</th>
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
                carImgListUrl={`${API_URL}/api/cars`}
                onCarSelected={handleCarSelected}
            />
        </div>
    );
}

export default NextRace;
