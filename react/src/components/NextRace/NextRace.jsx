import 'bootstrap/dist/css/bootstrap.min.css';
import './NextRace.css';
import { useState } from 'react';
import { useLoaderData } from 'react-router-dom';
import { Table, Container, Form, Button} from 'react-bootstrap';
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
        <Container>
            <h1>Next Race</h1>

            <Table responsive className="lane-assignments-table">
                <colgroup>
                    <col style={{width: "10%"}} />
                    <col style={{width: "10%"}} />
                    <col style={{width: "60%"}} />
                    <col style={{width: "10%"}} />
                    <col style={{width: "10%"}} />
                </colgroup>
                <thead>
                    <tr>
                        <th>Lane</th>
                        <th>Car</th>
                        <th>Driver</th>
                        <th>Raced</th>
                        <th>Sit&#8209;out</th>
                    </tr>
                </thead>
                <tbody>
                {laneAssignments.map(driver => (
                    <tr key={driver.lane_number} className={`lane-color-${driver.lane_color}`}>
                        <td className="lane-enabled-col">
                            <Form.Check
                                type="switch"
                                id={`lane-enabled-switch-${driver.lane_number}`}
                                checked={driver.lane_enabled}
                                onChange={(e) => handleLaneToggle(driver.lane_number, e.target.checked)}
                                className="lane-toggle"
                            />
                        </td>
                        <td className="car-image-col">
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
                        <td className="driver-name-col">{driver.driver_name}</td>
                        <td className="completed-races-col">{driver.completed_races}</td>
                        <td className="sit-out-col">
                            <Button
                                variant="outline-danger"
                                size="sm"
                                className="remove-button"
                                aria-label="Remove driver"
                            >
                                ×
                            </Button>
                        </td>
                    </tr>
                ))}
                </tbody>
            </Table>

            <h1>Other Drivers</h1>

            <Table responsive className="other-drivers-table">
                <colgroup>
                    <col style={{width: "00%"}} />
                    <col style={{width: "80%"}} />
                    <col style={{width: "10%"}} />
                    <col style={{width: "10%"}} />
                </colgroup>
                <thead>
                    <tr>
                        <td></td>
                        <th>Driver</th>
                        <th>Raced</th>
                        <th className="add-driver-col">Add</th>
                    </tr>
                </thead>
                <tbody>
                {otherDrivers.map(driver => (
                    <tr key={driver.id}>
                        <td></td>
                        <td className="driver-name-col">{driver.driver_name}</td>
                        <td className="completed-races-col">{driver.completed_races}</td>
                        <td className="add-driver-col">
                            <Button
                                variant="outline-success"
                                size="sm"
                                className="add-button"
                                aria-label="Add driver"
                            >
                                +
                            </Button>
                        </td>
                    </tr>
                ))}
                </tbody>
            </Table>

            <CarSelectorModal
                showMe={carSelectorLane !== null}
                onClose={() => setCarSelectorLane(null)}
                carImgListUrl={`${import.meta.env.VITE_API_URL}/api/cars`}
                onCarSelected={handleCarSelected}
            />

        </Container>
    );
}

export default NextRace;
