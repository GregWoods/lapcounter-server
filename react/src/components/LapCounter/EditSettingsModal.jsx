import './EditSettingsModal.css';
//import {useState} from 'react';
import ReactModal from 'react-modal';


const EditSettingsModal = ({ showMe, onClose, }) => 
{
    //copy parent state to local state so we can modify it independently 
    //  and save it only when the dialog is "Done""
    //const [localMqttHost, setLocalMqttHost] = useState(mqttHost);

    const onDone = () => {
        //setMqttHost(localMqttHost);
        onClose();
    }
    const onCancel = () => {
        //reset local _wsUrl, or it will be remembered next time the modal is opened. Feels clunky
        //setLocalMqttHost(mqttHost);
        onClose();
    }
 
    return (
        <ReactModal
            isOpen={showMe}
            onRequestClose={onCancel}
            id="editsettingsmodal"
            contentLabel="Edit Settings"
            closeTimeoutMS={400}
            className="ReactModalContent"
            overlayClassName="ReactModalOverlay"
            ariaHideApp={false}
        >
            <form onSubmit={evt => evt.preventDefault() }>
                <h2>Edit Settings</h2>
        
                <p>Description</p>
/
                <div>
                    <label htmlFor="blahInput">WebSocket URL</label>
                    <input id="blahInput" name="myInput" autoFocus
                    onChange={() => {
                        //setLocalMqttHost(evt.target.value)
                    }} />
                </div>

                <h2><button onClick={onDone}>Done</button></h2>
            </form>
        </ReactModal>
    );
}

export default EditSettingsModal;