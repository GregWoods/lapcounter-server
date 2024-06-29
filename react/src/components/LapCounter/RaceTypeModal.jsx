//https://github.com/astoilkov/use-local-storage-state
import useLocalStorageState from 'use-local-storage-state'
import RaceTypePreset from './RaceTypePreset'
import './RaceTypeModal.css'
import { useState, useEffect, createRef } from 'react';
import Modal from 'react-modal';


//maybe state management should be done on LapCounter
//note: LapCounter cannot handle time-based race duration yet. We would need a race timer,
//  and driver laps would need to count up

//ReactModal.setAppElement('#lapcounter');


const RaceTypeModal = ({ showMe, onClose, onStartCountdown }) => {

    //WARNING: at the moment, id must match array index
    //TODO: going to need a more comprehensive data structure for the different types of races
    // eslint-disable-next-line no-unused-vars
    const [raceDurationPresets, setRaceDurationPresets] = useLocalStorageState('racepresets', {
        ssr: true,
        defaultValue: [
            { id: 0, type: 'laps', description: 'Shakedown (6 laps)', details: { laps: 6 }},
            { id: 1, type: 'laps', description: 'Sprint (20 laps)', details: { laps: 20 }},
            { id: 2, type: 'laps', description: 'Standard (50 laps)', details: { laps: 50 }},
            { id: 3, type: 'laps', description: 'Professional (160 laps)', details: { laps: 160 }},
            /*{ id: 4, type: 'time', description: 'Endurance (60 minutes)', details: { time: '01:00:00' }},
            { id: 5, type: 'time', description: 'Le-Mans (4 hours)', details: { time: '04:00:00' }},
            { id: 6, type: 'lms', description: 'Last Man Standing\n(max 2 laps behind leader)', details: { maxLapsBehind: 2 }},*/
        ]        
    });


    //some "reduce" trickery to create an array which we can store a ref to each race preset
    //https://www.robinwieruch.de/react-scroll-to-item/
    //https://www.carlrippon.com/scrolling-a-react-element-into-view/
    //https://robinvdvleuten.nl/blog/scroll-a-react-component-into-view/
        const refs = raceDurationPresets.reduce((acc, preset) => {
        acc[preset.id] = createRef();
        return acc;
    }, {});

    //selection saved to local storage
    const [selectedPresetIdx, setSelectedPresetIdx] = useLocalStorageState('RaceTypeIdx', 2);

    const [modalClassName, setModalClassName] = useState("ReactModalContent");

    //WARNING: potential source of bugs is that we often use the array index and other times (refs) we use preset.id
    const handlePresetSelection = (idx) => {
        setSelectedPresetIdx(idx);
    }

    const handleStartRaceBtn = () => {
        //console.log('idx', selectedPresetIdxRef.current);
        console.log('idx', selectedPresetIdx);
        setModalClassName("ReactModalContent exitdown");
        //onStartCountdown(raceDurationPresets[selectedPresetIdxRef.current]);
        onStartCountdown(raceDurationPresets[selectedPresetIdx]);
    }

    useEffect(() => {
        if (refs[selectedPresetIdx] && refs[selectedPresetIdx].current) {
            refs[selectedPresetIdx].current.scrollIntoView({ behaviour: 'smooth', block: 'nearest' });
        }
    },
    [refs, selectedPresetIdx]);


    const handleKeyup = (evt) => {
        //evt.stopPropagation();    //maybe needed
        switch(evt.key) {
            case 'Enter':
                handleStartRaceBtn();
                break;
            case 'ArrowUp':
        setSelectedPresetIdx(idx => {
            const newIdx = (idx > 0) ? idx -= 1 : idx;
            console.log('ArrowUp. New idx', newIdx);
            return newIdx;
        });
                break;
            case 'ArrowDown':
                setSelectedPresetIdx(idx => {
                    const newIdx = (idx < raceDurationPresets.length - 1) ? idx += 1 : idx;
                    console.log('ArrowDn. New idx', newIdx);
                    return newIdx;
    });
                break;
        }
    }

    return (
        <Modal
            isOpen={showMe}
            onRequestClose={onClose}
            id="racetypemodal"
            contentLabel="Choose Race Type"
            closeTimeoutMS={800}
            className={modalClassName}
            overlayClassName="ReactModalOverlay"
            onAfterClose={() => setModalClassName('ReactModalContent')}     //reset modalClassName to default, so that closing the dialog slides it off the top of the screen
            onAfterOpen={() => document.getElementById("racePresetKeyboardFocus").focus()}      //needed for keyboard to work
            ariaHideApp={false}
        >
            <div id="racePresetKeyboardFocus" tabIndex="0" onKeyUp={handleKeyup}>
                <div id="racePresetList">
                    {
                        raceDurationPresets.map((preset, idx) => {
                            return (
                                <RaceTypePreset
                                    isSelected={idx === selectedPresetIdx}
                                    onSelect={handlePresetSelection}
                                    key={idx}
                                    myref={refs[preset.id]}
                                    presetIdx={idx}
                                    description={preset.description}
                                />
                            )
                        })
                    }
                </div>

                <div id="raceTypeFooter">
                    <button id="raceTypeStartRace" onClick={handleStartRaceBtn}>Start Race&nbsp;
                        <svg version="1.0" xmlns="http://www.w3.org/2000/svg" fill="#FFF" width="80"
                            viewBox="0 0 2399.5 2304" preserveAspectRatio="xMidYMid meet"
                            style={{ enableBackground: 'new 0 0 2399.5 2304', padding: '0px' }}
                        >
                            <g id="g4197">
                                <path fill="#000" id="path4145" d="M335.8,1345.9C151.3,819,0.2,386.8,0,385.6c-0.4-2,102.6-49.6,107.3-49.6c1,0,743.2,1889.5,744.2,1894.5
                                    c0.4,1.8-174.5,73.5-179.3,73.5C671.6,2304,520.2,1872.8,335.8,1345.9L335.8,1345.9z"/>
                                <path fill="#0A0" id="path4141" d="M479.2,1092.4c-221.5-563.1-287.6-732-286.8-733.3c7.9-12.8,103.4-85.2,156.3-118.6
                                    c226.2-142.5,522.5-212.7,817-193.8l10.5,0.7l237.4,534.2c130.6,293.8,237.6,534.1,237.8,533.9c0.2-0.2-52.6-196-117.2-435.2
                                    c-64.7-239.2-117.8-436.3-118.1-438l-0.5-3l17.3-3.8c222.7-48.6,369.8-114,489.6-217.6c7.5-6.5,15-13.3,16.7-15
                                    c1.7-1.7,3.5-3.1,4.2-3.1c1,0,455.2,1145.4,456.2,1150.7c0.7,3.7-13.8,27-29.3,46.8c-137.5,176.5-482,362.8-734.1,397
                                    c-156.4,21.2-262.5-15.1-311.3-106.6c-6.9-12.9-7.4-11.5,9.2-27.6c83.6-81.1,212.4-148.5,266.2-139.4
                                    c49.1,8.3,39.6,66.5-28.7,176.4l-6.9,11.2l5.8-6.1c212.4-225.5,188.8-339.3-50.5-243c-249,100.2-584.7,350-741.1,551.4
                                    c-5.7,7.3-10.6,13.2-11,13.2C767.5,1824,637.7,1494.8,479.2,1092.4L479.2,1092.4z"/>
                            </g>
                        </svg>
                    </button>

            </div>
        </div>
        </Modal>
    );
}

export default RaceTypeModal;