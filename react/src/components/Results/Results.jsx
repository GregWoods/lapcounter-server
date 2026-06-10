import { useLoaderData, Link } from 'react-router-dom';
import { House } from 'lucide-react';
import { useRef, useState, useLayoutEffect, useEffect } from 'react';
import MqttSubscriber from '../MqttSubscriber';
import './Results.css';

function posClass(pos) {
    if (!pos) return 'pos-dns';
    if (pos === 1) return 'pos-first';
    if (pos === 2) return 'pos-second';
    if (pos === 3) return 'pos-third';
    return 'pos-other';
}

function ResultsTable({ drivers, races, scrollRef }) {
    return (
        <div className="results-column" ref={scrollRef}>
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
    const loaded = useLoaderData() || { races: [], drivers: [], scoring_method: null, session_type: null, meeting_name: null };
    const [results, setResults] = useState(loaded);
    const { races, drivers, session_type, meeting_name } = results;
    const [wideView, setWideView] = useState(false);

    const refreshResults = () => {
        fetch(`${import.meta.env.VITE_API_URL}/sessions/active/results`)
            .then(r => r.ok ? r.json() : null)
            .then(data => { if (data) setResults(data); })
            .catch(() => {});
    };

    const lastRaceStateRef = useRef(null);
    const handleRaceState = (raceState) => {
        const prev = lastRaceStateRef.current;
        lastRaceStateRef.current = raceState.state;
        if (raceState.state !== prev && raceState.state === 'Finished') {
            refreshResults();
        }
    };

    const colRef = useRef(null);
    const col1Ref = useRef(null);
    const col2Ref = useRef(null);
    const [splitAt, setSplitAt] = useState(drivers.length);

    useLayoutEffect(() => {
        if (wideView) return;
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
    }, [drivers.length, wideView]);

    useEffect(() => {
        if (wideView) return;
        const c1 = col1Ref.current;
        const c2 = col2Ref.current;
        if (!c1 || !c2) return;

        const syncing = { current: false };
        const onScroll1 = () => {
            if (syncing.current) return;
            syncing.current = true;
            c2.scrollLeft = c1.scrollLeft;
            requestAnimationFrame(() => { syncing.current = false; });
        };
        const onScroll2 = () => {
            if (syncing.current) return;
            syncing.current = true;
            c1.scrollLeft = c2.scrollLeft;
            requestAnimationFrame(() => { syncing.current = false; });
        };

        c1.addEventListener('scroll', onScroll1);
        c2.addEventListener('scroll', onScroll2);
        return () => {
            c1.removeEventListener('scroll', onScroll1);
            c2.removeEventListener('scroll', onScroll2);
        };
    }, [wideView]);

    const col1 = drivers.slice(0, splitAt);
    const col2 = drivers.slice(splitAt);

    return (
        <div className="results-page">
            <MqttSubscriber
                mqttHost={import.meta.env.VITE_MQTT_URL}
                onRaceStateMessage={handleRaceState}
            />
            <div className="results-header">
                <Link to="/" className="home-icon-link"><House /></Link>
                <h1>Results{meeting_name ? `: ${meeting_name}` : ''}{session_type ? ` — ${session_type}` : ''}</h1>
                {races.length > 0 && (
                    <button className="view-toggle" onClick={() => setWideView(v => !v)} title={wideView ? 'Split view' : 'Wide view'}>
                        {wideView ? (
                            <svg width="20" height="16" viewBox="0 0 20 16" fill="currentColor">
                                <rect x="0" y="0" width="8" height="16" rx="1"/>
                                <rect x="12" y="0" width="8" height="16" rx="1"/>
                            </svg>
                        ) : (
                            <svg width="20" height="16" viewBox="0 0 20 16" fill="currentColor">
                                <rect x="0" y="0" width="20" height="16" rx="1"/>
                            </svg>
                        )}
                    </button>
                )}
            </div>
            {races.length === 0 ? (
                <p className="no-results">No races completed yet.</p>
            ) : wideView ? (
                <div className="results-columns results-columns--wide">
                    <ResultsTable drivers={drivers} races={races} scrollRef={col1Ref} />
                </div>
            ) : (
                <div className="results-columns" ref={colRef}>
                    <ResultsTable drivers={col1} races={races} scrollRef={col1Ref} />
                    <ResultsTable drivers={col2} races={races} scrollRef={col2Ref} />
                </div>
            )}
        </div>
    );
}

export default Results;
