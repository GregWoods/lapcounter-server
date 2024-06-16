import './RaceTypePreset.css'


const RaceTypePreset = ({isSelected, onSelect, presetIdx, description, myref}) => {

    const handleSelect = (evt) => {
        onSelect(Number(evt.target.value));
    }

    const selectedStateCssClass = 'raceDurationPreset isSelected' + isSelected;
    
    return (
        <button
            className={selectedStateCssClass} 
            onClick={handleSelect}
            value={presetIdx}
            ref={myref}
        >
            {description}
        </button>
    )
}

export default RaceTypePreset;