import PageHeader from '../PageHeader/PageHeader';

// Display-only currentrace header — shares PageHeader with /nextrace.
// Shows "Session N, Race M of Y" + status suffix ("- Results" / "- Get Ready!").
// "of Y" appears only for sessions with a races_per_driver target (total known up front).
function Header({ sessionNumber, raceNumber, sessionRacesTotal, racePhase }) {
    const suffix = racePhase === 'results' ? ' - Results'
        : racePhase === 'getready' ? ' - Get Ready!'
            : '';
    const sessionPrefix = sessionNumber ? `Session ${sessionNumber}, ` : '';
    const raceCount = sessionRacesTotal ? ` of ${sessionRacesTotal}` : '';
    const title = raceNumber ? `${sessionPrefix}Race ${raceNumber}${raceCount}${suffix}` : '';
    return <PageHeader title={title} />;
}

export default Header;
