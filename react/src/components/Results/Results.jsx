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

function fmtLap(t) {
    if (t == null) return '–';
    const s = Number(t).toFixed(3);          // e.g. "4.523" or "12.523"
    const intLen = s.indexOf('.');
    // Pad single-digit seconds with a figure space (digit-width) so columns of
    // single- and double-digit lap times line up on the decimal point.
    return intLen < 2 ? ' '.repeat(2 - intLen) + s : s;
}

// Rank drivers within each race by best lap (ascending) so the fastest three lap
// times in each race can be medalled gold / silver / bronze. Returns
// { [race_id]: { [driver_id]: position } }. Must be fed the full field, not a
// single display column, so positions are correct across the whole race.
function computeRaceRanks(drivers, races) {
    const ranks = {};
    for (const r of races) {
        const key = String(r.race_id);
        const order = drivers
            .map(d => ({ id: d.driver_id, t: d.lap_times?.[key] }))
            .filter(e => e.t != null)
            .sort((a, b) => a.t - b.t);
        const m = {};
        order.forEach((e, i) => { m[e.id] = i + 1; });
        ranks[key] = m;
    }
    return ranks;
}

function ResultsTable({ drivers, races, scrollRef, startIndex = 0 }) {
    return (
        <div className="results-column" ref={scrollRef}>
            <table className="results-table results-table--points">
                <thead>
                    <tr>
                        <th className="posn-col">Pos</th>
                        <th className="driver-col">Driver</th>
                        <th className="total-col">Pts</th>
                        <th className="raced-col">Raced</th>
                        {[...races].reverse().map(r => (
                            <th key={r.race_id} className="race-col">R{r.race_number}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {drivers.map((d, i) => (
                        <tr key={d.driver_id}>
                            <td className="posn-cell">{startIndex + i + 1}</td>
                            <td className="driver-name-cell">{d.driver_name}</td>
                            <td className="total-cell">{d.total_points}</td>
                            <td className="raced-cell">{d.races_entered}</td>
                            {[...races].reverse().map(r => {
                                const key = String(r.race_id);
                                const pos = d.positions[key];
                                const pts = d.points?.[key];
                                return (
                                    <td key={r.race_id} className={`position-cell ${posClass(pos)}`}>
                                        {pos == null ? '–' : pts}
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

function FastestLapResultsTable({ drivers, races, scrollRef, scoringMethod, raceRanks, startIndex = 0 }) {
    const totalLabel = scoringMethod === 'AverageFastestLap' ? 'Avg Lap' : 'Best Lap';
    return (
        <div className="results-column" ref={scrollRef}>
            <table className="results-table results-table--fastestlap">
                <thead>
                    <tr>
                        <th className="posn-col">Pos</th>
                        <th className="driver-col">Driver</th>
                        <th className="total-col">{totalLabel}</th>
                        <th className="raced-col">Raced</th>
                        {[...races].reverse().map(r => (
                            <th key={r.race_id} className="race-col">R{r.race_number}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {drivers.map((d, i) => (
                        <tr key={d.driver_id}>
                            <td className="posn-cell">{startIndex + i + 1}</td>
                            <td className="driver-name-cell">{d.driver_name}</td>
                            <td className="total-cell fl-lap">{fmtLap(d.total_lap_time)}</td>
                            <td className="raced-cell">{d.races_entered}</td>
                            {[...races].reverse().map(r => {
                                const key = String(r.race_id);
                                const t = d.lap_times?.[key];
                                const empty = t == null;
                                const rank = empty ? null : raceRanks?.[key]?.[d.driver_id];
                                return (
                                    <td key={r.race_id} className={`position-cell ${rank ? posClass(rank) : 'pos-other'} fl-lap${empty ? ' fl-empty' : ''}`}>
                                        {fmtLap(t)}
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
    const SESSION_TYPE_LABELS = { Points: 'Points', FastestLap: 'Fastest Lap', Championship: 'Championship' };

    const loaded = useLoaderData();
    const [results, setResults] = useState(loaded);
    const {
        races = [], drivers = [], sessions = [],
        meeting_name = null, session_id, session_type = null, scoring_method = null,
    } = results || {};
    const isFastestLap = session_type === 'FastestLap';

    useEffect(() => {
        setResults(loaded);
        setWideView(false);
    }, [loaded]);

    const tabLabel = (s, index) =>
        `Session ${index + 1} — ${SESSION_TYPE_LABELS[s.session_type] || s.session_type}`;

    const [wideView, setWideView] = useState(false);

    const refreshResults = () => {
        fetch(`${import.meta.env.VITE_API_URL}/sessions/current/results`)
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
    // Medal ranks computed from the full field so they stay correct when the
    // table is split into two display columns.
    const raceRanks = isFastestLap ? computeRaceRanks(drivers, races) : null;

    return (
        <div className="results-page">
            <MqttSubscriber
                mqttHost={import.meta.env.VITE_MQTT_URL}
                onRaceStateMessage={handleRaceState}
            />
            <div className="results-header">
                <Link to="/" className="home-icon-link"><House /></Link>
                <h1>Results{meeting_name ? ` — ${meeting_name}` : ''}</h1>
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
            {sessions.length > 1 && (
                <nav className="session-tabs">
                    {sessions.map((s, idx) => (
                        <Link
                            key={s.id}
                            to={`/results/${s.id}`}
                            className={[
                                'session-tab',
                                s.id === session_id ? 'session-tab--active' : '',
                                s.state === 'InProgress' ? 'session-tab--inprogress' : '',
                                s.state === 'NotStarted' ? 'session-tab--notstarted' : '',
                            ].filter(Boolean).join(' ')}
                        >
                            {tabLabel(s, idx)}
                        </Link>
                    ))}
                </nav>
            )}
            {races.length === 0 ? (
                <p className="no-results">No races completed yet.</p>
            ) : wideView ? (
                <div className="results-columns results-columns--wide">
                    {isFastestLap
                        ? <FastestLapResultsTable drivers={drivers} races={races} scrollRef={col1Ref} scoringMethod={scoring_method} raceRanks={raceRanks} />
                        : <ResultsTable drivers={drivers} races={races} scrollRef={col1Ref} />}
                </div>
            ) : (
                <div className="results-columns" ref={colRef}>
                    {isFastestLap ? (
                        <>
                            <FastestLapResultsTable drivers={col1} races={races} scrollRef={col1Ref} scoringMethod={scoring_method} raceRanks={raceRanks} startIndex={0} />
                            <FastestLapResultsTable drivers={col2} races={races} scrollRef={col2Ref} scoringMethod={scoring_method} raceRanks={raceRanks} startIndex={splitAt} />
                        </>
                    ) : (
                        <>
                            <ResultsTable drivers={col1} races={races} scrollRef={col1Ref} startIndex={0} />
                            <ResultsTable drivers={col2} races={races} scrollRef={col2Ref} startIndex={splitAt} />
                        </>
                    )}
                </div>
            )}
        </div>
    );
}

export default Results;
