import {useState, useEffect, useRef, createRef} from 'react';
import ReactModal from 'react-modal';
import RaceFlagStart from './RaceFlagStart';
import './YellowFlag.css';



const YellowFlagRacePaused = ({showMe, onRacePaused, onEndYellowFlag}) => {

    const [yfFlashingPeriod, setYfFlashingPeriod] = useState(null);
    const [yfClassName, setYfClassName] = useState('black');

    
    //todo: move to separate file
    const useInterval = (callback, delay) => {
        const savedCallback = useRef();
      
        useEffect(() => {
          savedCallback.current = callback;
        }, [callback]);
      
        useEffect(() => {
            const tick = () => {
                savedCallback.current();
            }
            if (delay !== null) {
                let id = setInterval(tick, delay);
                return () => clearInterval(id);
            }
        }, [delay]);
    };


    useInterval(() => {
        setYfClassName(prevValue => prevValue == 'yellow' ? 'black' : 'yellow');
        console.log("interval");
    }, yfFlashingPeriod);


    const pauseRace = () => {
        console.log('_-_-_- startYellowFlashing _-_-_-_-');
        setYfFlashingPeriod(500);
        onRacePaused();
    }


    const handleEndYellowFlag = () => {
        console.log("Yellow flag end");
        setYfFlashingPeriod(null);
        onEndYellowFlag();
    }


    //needed for onKeyUp
    const yellowFlagRef = createRef();
    useEffect(() => {
        if (yellowFlagRef.current) {
            yellowFlagRef.current.focus();
        }
    }, [yellowFlagRef]);


    const handleKeyup = (evt) => {
        console.log(evt.key);
        if (showMe && evt.key == ' ') {
            handleEndYellowFlag();  
        }
    }


    return (
        <ReactModal
            isOpen={showMe}
            contentLabel="YelloW Flag"
            onAfterOpen={pauseRace}
            className="yellowflag"
            overlayClassName="racePausedModalOverlay"
            ariaHideApp={false}
        >   
            
            <div id="yellowflagcontainer" ref={yellowFlagRef} tabIndex={0} onKeyUp={handleKeyup}>
                <div id="yellowflagheader">
                    <RaceFlagStart 
                        onSelect={handleEndYellowFlag} 
                        handleColor='#000' />
                    <h1>Yellow Flag - Race Paused</h1>
                </div>
                <div id="yellowflagcontent" className={yfClassName}>
                </div>
            </div>
        </ReactModal>
    );
}

export default YellowFlagRacePaused;