import './EditSettingsModal.css';
import {useState} from 'react';
import ReactModal from 'react-modal';


const EditSettingsModal = ({ showMe, onClose, mqttHost, setMqttHost }) => 
{
    //copy parent state to local state so we can modify it independently 
    //  and save it only when the dialog is "Done""
    const [localMqttHost, setLocalMqttHost] = useState(mqttHost);

    const onDone = () => {
        setMqttHost(localMqttHost);
        onClose();
    }
    const onCancel = () => {
        //reset local _wsUrl, or it will be remembered next time the modal is opened. Feels clunky
        setLocalMqttHost(mqttHost);
        onClose();
    }
 
    return (
        <ReactModal
            isOpen={showMe}
            onRequestClose={onCancel}
            id="editsettingsmodal"
            contentLabel="Edit Settings"
            closeTimeoutMS={600}
            className="ReactModalContent"
            overlayClassName="ReactModalOverlay"
            ariaHideApp={false}
        >
            <form onSubmit={evt => evt.preventDefault() }>
                <h2>Edit Settings</h2>
        
                <p>For Raspi3A version, running Chromium on the PI with a connected monitor, this value is 
                <b> ws://127.0.0.1:8080</b></p>
                <p>If you are running this on a remote web browser, you need to find the IP address of the 
                    Raspberry Pi and use that value in place of 127.0.0.1</p>
                <div>
                    <label htmlFor="config_wsaddress">WebSocket URL</label>
                    <input id="config_wsaddress" name="wsurl" autoFocus
                    onChange={(evt) => {setLocalMqttHost(evt.target.value)}}
                    value={localMqttHost} />
                </div>

                <h2><button onClick={onDone}>Done</button></h2>
            </form>
        </ReactModal>
    );
}

export default EditSettingsModal;