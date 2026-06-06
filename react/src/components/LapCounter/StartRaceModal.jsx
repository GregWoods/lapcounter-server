import 'bootstrap/dist/css/bootstrap.min.css';
import { Modal, Button } from 'react-bootstrap';

function StartRaceModal({ showMe, onStart, onClose }) {
    return (
        <Modal show={showMe} onHide={onClose} centered size="xl">
            <Modal.Header closeButton>
                <Modal.Title>Next Race</Modal.Title>
            </Modal.Header>
            <Modal.Body className="text-center">
                <Button variant="success" size="lg" onClick={onStart}>
                    Start
                </Button>
            </Modal.Body>
        </Modal>
    );
}

export default StartRaceModal;
