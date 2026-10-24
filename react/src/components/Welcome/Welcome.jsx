import { useEffect, useState } from 'react';
import { Link, useRouteLoaderData } from 'react-router-dom';
import { House } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import { API_URL } from '../../endpoints.js';
import { wifiQrPayload, meetingUrl } from './wifiQr.js';
import NoMeeting from './NoMeeting.jsx';
import './Welcome.css';

// TV-first landing page: scan 1 to join the WiFi, scan 2 to open the meeting.
export default function Welcome() {
    const meeting = useRouteLoaderData('meeting');
    const [settings, setSettings] = useState(null);
    const ended = !!meeting.ended_at;

    useEffect(() => {
        fetch(`${API_URL}/settings`)
            .then(r => (r.ok ? r.json() : null))
            .then(setSettings)
            .catch(() => setSettings(null));
    }, []);

    if (ended) return <NoMeeting />;
    if (!settings) return <div className="welcome-page" />;

    const wifi = wifiQrPayload(settings);
    const url = meetingUrl(settings.public_base_url, window.location.origin);

    return (
        <div className="welcome-page">
            <Link to={`/m/${meeting.public_id}`} className="home-icon-link welcome-home" title="Home"><House /></Link>
            <h1 className="welcome-title">{meeting.name}</h1>
            <div className="welcome-codes">
                {wifi && (
                    <section className="welcome-code">
                        <h2>1. Join the WiFi</h2>
                        <div className="welcome-qr"><QRCodeSVG value={wifi} size={360} marginSize={2} /></div>
                        <p className="welcome-detail">{settings.wifi_ssid}</p>
                        {settings.wifi_security !== 'nopass' && settings.wifi_password && (
                            <p className="welcome-detail">Password: {settings.wifi_password}</p>
                        )}
                    </section>
                )}
                <section className="welcome-code">
                    <h2>{wifi ? '2. Open the meeting' : 'Open the meeting'}</h2>
                    <div className="welcome-qr"><QRCodeSVG value={url} size={360} marginSize={2} /></div>
                    <p className="welcome-detail">{url}</p>
                </section>
            </div>
        </div>
    );
}
