import 'bootstrap/dist/css/bootstrap.min.css';
import { Modal, Button } from 'react-bootstrap';

function StartRaceModal({ showMe, onStart, onClose }) {
    return (
        <Modal show={showMe} onHide={onClose} centered size="sm">
            <Modal.Header closeButton>
                <Modal.Title>Next Race</Modal.Title>
            </Modal.Header>
            <Modal.Body className="text-center">
                <Button variant="success" size="lg" onClick={onStart}>
                    Start Race
                </Button>
            </Modal.Body>
        </Modal>
    );
}

export default StartRaceModal;
