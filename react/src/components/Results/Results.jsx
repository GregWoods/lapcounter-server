import { useLoaderData } from 'react-router-dom';
import './Results.css';

function posClass(pos) {
    if (!pos) return 'pos-dns';
    if (pos === 1) return 'pos-first';
    if (pos === 2) return 'pos-second';
    if (pos === 3) return 'pos-third';
    return 'pos-other';
}

function Results() {
    const data = useLoaderData() || { races: [], drivers: [] };
    const { races, drivers } = data;

    return (
        <div className="results-page">
            <h1>Race Results</h1>
            {races.length === 0 ? (
                <p className="no-results">No races completed yet.</p>
            ) : (
                <div className="results-table-wrapper">
                    <table className="results-table">
                        <thead>
                            <tr>
                                <th className="driver-col">Driver</th>
                                {races.map(r => (
                                    <th key={r.race_id} className="race-col">R{r.race_number}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {drivers.map(d => (
                                <tr key={d.driver_id}>
                                    <td className="driver-name-cell">{d.driver_name}</td>
                                    {races.map(r => {
                                        const pos = d.positions[String(r.race_id)];
                                        return (
                                            <td key={r.race_id} className={`position-cell ${posClass(pos)}`}>
                                                {pos ?? '–'}
                                            </td>
                                        );
                                    })}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}

export default Results;
