import 'bootstrap/dist/css/bootstrap.min.css';
import './NextRace.css';
import { useLoaderData } from 'react-router-dom';
import { Table, Container, Form, Button} from 'react-bootstrap';


function NextRace() {
    const next_race_setup = useLoaderData();
    const lane_assignments = next_race_setup.lane_assignments;
    const other_drivers = next_race_setup.other_drivers;

    return (
        <Container>
            <h1>Next Race</h1>

            <Table responsive className="lane-assignments-table">
                <colgroup>
                    <col style={{width: "10%"}} />
                    <col style={{width: "70%"}} />
                    <col style={{width: "10%"}} />
                    <col style={{width: "10%"}} />
                </colgroup>                
                <thead>
                    <tr>
                        <th>Lane</th>
                        <th>Driver</th>
                        <th>Raced</th>
                        <th>Sit&#8209;out</th>
                    </tr>
                </thead>
                <tbody>
                {lane_assignments.map(driver => (
                    <tr key={driver.id} className={`lane-color-${driver.lane_color}`}>
                        <td className="lane-enabled-col">
                            <Form.Check 
                                type="switch"
                                id={`lane-enabled-switch-${driver.id}`}
                                defaultChecked={true}
                                className="lane-toggle"
                            />
                        </td>
                        <td className="driver-name-col">{driver.first_name}</td>
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
                {other_drivers.map(driver => (
                    <tr key={driver.id}>
                        <td></td>
                        <td className="driver-name-col">{driver.first_name}</td>
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

        </Container>
    );
}

export default NextRace;