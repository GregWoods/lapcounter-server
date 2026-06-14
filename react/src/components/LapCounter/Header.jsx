import PageHeader from '../PageHeader/PageHeader';

// Display-only currentrace header — shares PageHeader with /nextrace.
// Shows the race number + status suffix ("- Results" / "- Get Ready!").
function Header({ raceNumber, racePhase }) {
    const suffix = racePhase === 'results' ? ' - Results'
        : racePhase === 'getready' ? ' - Get Ready!'
            : '';
    const title = raceNumber ? `Race ${raceNumber}${suffix}` : '';
    return <PageHeader title={title} />;
}

export default Header;
