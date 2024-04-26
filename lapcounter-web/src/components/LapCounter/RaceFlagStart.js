
//https://en.wikipedia.org/wiki/Racing_flags#Green_flag

const RaceFlagStart = ({onSelect, handleColor, children}) => {
    return (
        <button id="btnStartRace" className="button" onClick={onSelect}>
            <svg version="1.0" xmlns="http://www.w3.org/2000/svg" fill="#FFF" width="100"
                viewBox="0 0 2399.5 2304" preserveAspectRatio="xMidYMid meet"
                style={{enableBackground:'new 0 0 2399.5 2304'},{padding:'0px'}}
                >
                <g id="g4197">
                    <path fill={handleColor} id="path4145" d="M335.8,1345.9C151.3,819,0.2,386.8,0,385.6c-0.4-2,102.6-49.6,107.3-49.6c1,0,743.2,1889.5,744.2,1894.5
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
            {children}
        </button>
    );
}

export default RaceFlagStart;