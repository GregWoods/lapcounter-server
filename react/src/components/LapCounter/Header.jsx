import './Header.css';
import EditSettingsModal from './EditSettingsModal';
import React, { useState } from 'react';
import ResetFastestLapTodayModal from './ResetFastestLapTodayModal';


// Race-control flag buttons now live on the PIN-protected /racecontrol page.
// This header is display-only: race number + status suffix and the lap record.
function Header({
    raceNumber,
    racePhase,        // 'results' | 'getready' | 'live'
    mqttHost, setMqttHost,
    fastestLapToday,
    resetFastestLapToday }) {

    const [settingsModalShown, setSettingsModalShown] = useState(false);
    const [resetFastestLapTodayModalShown, setResetFastestLapTodayModalShown] = useState(false);

    const suffix = racePhase === 'results' ? ' - Results'
        : racePhase === 'getready' ? ' - Get Ready!'
            : '';

    return (
        <React.Fragment>
            <div id="header">
                <h1>{raceNumber ? `Race ${raceNumber}${suffix}` : ''}</h1>

                <div id="laprecord" onClick={() => { setResetFastestLapTodayModalShown(true); }}>
                    <div id="laprecordlbl">Lap Record</div>
                    <div id="fastestlaptime">{fastestLapToday}</div>
                </div>
            </div>

            <EditSettingsModal
                showMe={settingsModalShown}
                onClose={() => setSettingsModalShown(false)}
                mqttHost={mqttHost}
                setMqttHost={setMqttHost}
            />

            <ResetFastestLapTodayModal
                showMe={resetFastestLapTodayModalShown}
                onClose={() => setResetFastestLapTodayModalShown(false)}
                resetFastestLapToday={resetFastestLapToday}
            />
        </React.Fragment>
    );
}

export default Header;
