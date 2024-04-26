import './Header.css';
import RaceFlagStart from './RaceFlagStart'
import RaceFlagEnd from './RaceFlagEnd'
import StartLights from './StartLights';
import RaceTypeModal from './RaceTypeModal';
import EditSettingsModal from './EditSettingsModal';
import React, { useState, useEffect, createRef } from 'react';
import RaceFlagYellow from './RaceFlagYellow';
import YellowFlagCountdown from './YellowFlagCountdown';
import YellowFlagRacePaused from './YellowFlagRacePaused';
import ResetFastestLapModal from './ResetFastestLapModal';


function Header({
    wsUrl, setWsUrl, 
    onGoGoGo, 
    onStartCountdown,
    fastestLapToday, 
    hasRaceStarted, 
    onRaceEnd,
    yellowFlagAdvantageDuration,
    onYellowFlagCountdown,
    onYellowFlag, 
    onEndYellowFlag,
    resetTodaysFastestLap }) {

    const [showStartLights, setShowStartLights] = useState(false);

    // eslint-disable-next-line no-unused-vars
    const [raceTypeModalShown, setRaceTypeModalShown] = useState(false);
    const [settingsModalShown, setSettingsModalShown] = useState(false);
    const [yellowCountdownShown, setYellowCountdownShown] = useState(false);
    const [yellowFlashingShown, setYellowFlashingShown] = useState(false);
    const [resetFastestLapModalShown, setResetFastestLapModalShown] = useState(false);


    //needed for onKeyUp
    const headerRef = createRef();
    useEffect(() => {
        if (headerRef) {
            headerRef.current.focus();
        }
    }, [headerRef]);

    const handleStartCountdown = (raceTypeObj) => {
        console.log("Header:handleStartCountdown", raceTypeObj);
        onStartCountdown(raceTypeObj);
        setRaceTypeModalShown(false);
        setShowStartLights(true);
    }

    const handleGoGoGo = () => {
        console.log("Go! Go! Go!");
        onGoGoGo();
    }

    const closeStartLights = () => {
        setShowStartLights(false);
    }

    // eslint-disable-next-line no-unused-vars
    const handleRaceEnd = () => {
        console.log("Header:handleRaceEnd");
        onRaceEnd();
    }

    const handleYellowFlagCountdown = () => {
        setYellowCountdownShown(true);
        onYellowFlagCountdown();
    }

    const handleRacePaused = () => {
        onYellowFlag();
    }

    const handleOnEndYellowFlagCountdown = () => {
        console.log("_-_-_- END Yellow Flag Countdown -_-_-_");
        //hide the countdown dialog and show the race paused dialog
        setYellowCountdownShown(false);
        setYellowFlashingShown(true);
    }

    const handleEndYellowFlag = () => {
        setYellowCountdownShown(false);
        setYellowFlashingShown(false);
        onEndYellowFlag();
        console.log("header: end yellow flag");
    }

    const handleKeyup = (evt) => {
        console.log(evt.key);
        if (hasRaceStarted && evt.key == ' ') {
            if (!yellowCountdownShown && !yellowFlashingShown) {
                handleYellowFlagCountdown();
            }
        }
    }

    return (
        <React.Fragment>
            <div id="header" ref={headerRef} tabIndex={0} onKeyUp={handleKeyup}>

                <button id="btnSettings" className="button" href="#" alt="Settings" 
                    data-toggle="modal" data-target="#configModal"
                    onClick={() => {setSettingsModalShown(true)}}
                >
                    <svg id="icon-settings" fill="#FFF" viewBox="0 0 24 24" width="48" height="48"
                        xmlns="http://www.w3.org/2000/svg">
                        <path d="M0 0h24v24H0z" fill="none" />
                        <path
                            d="M19.43 12.98c.04-.32.07-.64.07-.98s-.03-.66-.07-.98l2.11-1.65c.19-.15.24-.42.12-.64l-2-3.46c-.12-.22-.39-.3-.61-.22l-2.49 1c-.52-.4-1.08-.73-1.69-.98l-.38-2.65C14.46 2.18 14.25 2 14 2h-4c-.25 0-.46.18-.49.42l-.38 2.65c-.61.25-1.17.59-1.69.98l-2.49-1c-.23-.09-.49 0-.61.22l-2 3.46c-.13.22-.07.49.12.64l2.11 1.65c-.04.32-.07.65-.07.98s.03.66.07.98l-2.11 1.65c-.19.15-.24.42-.12.64l2 3.46c.12.22.39.3.61.22l2.49-1c.52.4 1.08.73 1.69.98l.38 2.65c.03.24.24.42.49.42h4c.25 0 .46-.18.49-.42l.38-2.65c.61-.25 1.17-.59 1.69-.98l2.49 1c.23.09.49 0 .61-.22l2-3.46c.12-.22.07-.49-.12-.64l-2.11-1.65zM12 15.5c-1.93 0-3.5-1.57-3.5-3.5s1.57-3.5 3.5-3.5 3.5 1.57 3.5 3.5-1.57 3.5-3.5 3.5z" />
                    </svg>
                </button>

                {
                    !hasRaceStarted &&
                    <RaceFlagStart 
                        onSelect={() => setRaceTypeModalShown(true)}
                        handleColor='#FFF'
                    />
                }
                {
                    hasRaceStarted &&
                    <RaceFlagEnd 
                        onSelect={handleRaceEnd}
                    />
                }
                {   hasRaceStarted &&
                    <RaceFlagYellow 
                        onSelect={handleYellowFlagCountdown}
                    />                    
                }

                <h1>Wellington Raceway</h1>
                    
                <div id="laprecord" onClick={() => {setResetFastestLapModalShown(true)}}>
                    <div id="laprecordlbl">Lap Record</div>
                    <div id="fastestlaptime">{fastestLapToday}</div>
                </div>

            </div>


            <EditSettingsModal 
                showMe={settingsModalShown}
                onClose={() => setSettingsModalShown(false)}
                wsUrl={wsUrl}
                setWsUrl={setWsUrl}
            />

            <RaceTypeModal
                showMe={raceTypeModalShown}
                onClose={() => setRaceTypeModalShown(false)}
                onStartCountdown={handleStartCountdown}
            />


            <StartLights
                showMe={showStartLights}
                onClose={closeStartLights}
                onLightsOut={handleGoGoGo}
            />

            
            <YellowFlagCountdown
                showMe={yellowCountdownShown} 
                onEndCountdown={handleOnEndYellowFlagCountdown}
                yellowFlagAdvantageDuration={yellowFlagAdvantageDuration} />


            <YellowFlagRacePaused
                showMe={yellowFlashingShown} 
                onRacePaused={handleRacePaused}
                onEndYellowFlag={handleEndYellowFlag} />

                        
            <ResetFastestLapModal 
                showMe={resetFastestLapModalShown}
                onClose={() => setResetFastestLapModalShown(false)}
                resetFastestLap = {resetTodaysFastestLap}
            />    

                
        </React.Fragment>
    );
}

export default Header;