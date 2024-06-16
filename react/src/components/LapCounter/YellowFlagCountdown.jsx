import {useState, useEffect, useRef} from 'react';
import ReactModal from 'react-modal';
import './YellowFlag.css';



const YellowFlagCountdown = ({showMe, onEndCountdown, yellowFlagAdvantageDuration}) => {

    const [yfCountdownPeriod, setYfCountdownPeriod] = useState(null);
    const [yfCountdownFloat, setYfCountdownFloat] = useState(yellowFlagAdvantageDuration);

    
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


    //useInterval should be inside top level of component.
    //  we control when it starts by setting the interval value (null means it won't run)
    useInterval(() => {
        setYfCountdownFloat((oldValue) => {
            const newValue = (oldValue) - (yfCountdownPeriod /1000);
            if (newValue > 0.0) {
                return newValue;
            } else {
                setYfCountdownPeriod(null)
                onEndCountdown();
                return 0.0;
            }
        });
    }, yfCountdownPeriod);


    const startCountdown = () => {
        console.log('YellowFlagCountdown:', yellowFlagAdvantageDuration);
        setYfCountdownFloat(yellowFlagAdvantageDuration);
        setYfCountdownPeriod(100);  //Countdown is in tenths of a second
    }
  
    const yfCountdown = parseFloat(yfCountdownFloat).toFixed(1);

    return (
        <ReactModal
            isOpen={showMe}
            //onRequestClose={onClose}
            contentLabel="YelloW Flag"
            //closeTimeoutMS={1050}
            className="yellowflag"
            overlayClassName="yellowflagModalOverlay"
            onAfterOpen={() => startCountdown()}
            ariaHideApp={false}
        >   
            
            <div id="yellowflagcontainer">
                <div id="yellowflagheader">
                    <h1>Yellow Flag Countdown</h1>
                </div>
                <div id="yellowflagcontent">
                    <div id="yellowflagcountdown">
                        {yfCountdown}
                    </div>
                </div>
            </div>
        </ReactModal>
    );
}

export default YellowFlagCountdown;