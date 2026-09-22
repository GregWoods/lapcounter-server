import { useId } from 'react';

// Chequered-flag icon shared by the home menu and the race-control End button.
// This is the lucide `Flag` icon (same banner shape + staff used for "Current
// Race"), tilted as if waved and with a checker grid clipped into the banner.
// Stroke-based so it inherits the same `stroke-width`/sizing CSS as lucide icons.
const BANNER = 'M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z';

export default function ChequeredFlagIcon(props) {
    const clipId = `cf-${useId().replace(/:/g, '')}`;
    return (
        <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            {...props}
        >
            <g transform="rotate(12 4 22)">
                <defs>
                    <clipPath id={clipId}>
                        <path d={BANNER} />
                    </clipPath>
                </defs>
                {/* checker squares, clipped to the banner outline */}
                <g clipPath={`url(#${clipId})`} stroke="none" fill="currentColor">
                    <rect x="4" y="3" width="4" height="4" />
                    <rect x="12" y="3" width="4" height="4" />
                    <rect x="8" y="7" width="4" height="4" />
                    <rect x="16" y="7" width="4" height="4" />
                    <rect x="4" y="11" width="4" height="4" />
                    <rect x="12" y="11" width="4" height="4" />
                </g>
                {/* banner outline + staff (lucide Flag) */}
                <path d={BANNER} />
                <line x1="4" y1="22" x2="4" y2="15" />
            </g>
        </svg>
    );
}
