import { useLoaderData } from 'react-router-dom';
import { useRef, useState, useLayoutEffect } from 'react';
import './Results.css';

function posClass(pos) {
    if (!pos) return 'pos-dns';
    if (pos === 1) return 'pos-first';
    if (pos === 2) return 'pos-second';
    if (pos === 3) return 'pos-third';
    return 'pos-other';
}

function ResultsTable({ drivers, races }) {
    return (
        <div className="results-column">
            <table className="results-table">
                <thead>
                    <tr>
                        <th className="driver-col">Driver</th>
                        <th className="total-col">Points</th>
                        <th className="raced-col">Raced</th>
                        {[...races].reverse().map(r => (
                            <th key={r.race_id} className="race-col">R{r.race_number}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {drivers.map(d => (
                        <tr key={d.driver_id}>
                            <td className="driver-name-cell">{d.driver_name}</td>
                            <td className="total-cell">{d.total_points}</td>
                            <td className="raced-cell">{d.races_entered}</td>
                            {[...races].reverse().map(r => {
                                const pos = d.positions[String(r.race_id)];
                                return (
                                    <td key={r.race_id} className={`position-cell ${posClass(pos)}`}>
                                        {pos == null ? '–' : pos}
                                    </td>
                                );
                            })}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function Results() {
    const data = useLoaderData() || { races: [], drivers: [], scoring_method: null };
    const { races, drivers } = data;

    const colRef = useRef(null);
    // Start with all drivers in col1; useLayoutEffect corrects this before first paint.
    const [splitAt, setSplitAt] = useState(drivers.length);

    useLayoutEffect(() => {
        const measure = () => {
            const col = colRef.current;
            if (!col || !drivers.length) return;
            const thead = col.querySelector('thead');
            const firstRow = col.querySelector('tbody tr');
            if (!thead || !firstRow) return;
            const rowsPerCol = Math.floor(
                (col.clientHeight - thead.offsetHeight) / firstRow.offsetHeight
            );
            setSplitAt(Math.max(1, Math.min(rowsPerCol, drivers.length)));
        };

        measure();
        const ro = new ResizeObserver(measure);
        if (colRef.current) ro.observe(colRef.current);
        return () => ro.disconnect();
    }, [drivers.length]);

    const col1 = drivers.slice(0, splitAt);
    const col2 = drivers.slice(splitAt);

    return (
        <div className="results-page">
            <h1>Session Results</h1>
            {races.length === 0 ? (
                <p className="no-results">No races completed yet.</p>
            ) : (
                <div className="results-columns" ref={colRef}>
                    <ResultsTable drivers={col1} races={races} />
                    <ResultsTable drivers={col2} races={races} />
                </div>
            )}
        </div>
    );
}

export default Results;
