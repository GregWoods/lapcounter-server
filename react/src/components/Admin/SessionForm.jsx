import { useState } from 'react';
import './Admin.css';

// Race types offered in the session form. 'Points' = Finishing Position (race ends on
// laps, scored by position); 'FastestLap' = Fastest Lap (race ends on time, personal best).
const RACE_TYPES = ['Points', 'FastestLap'];
const SESSION_TYPE_LABELS = { Points: 'Finishing Position', FastestLap: 'Fastest Lap', Championship: 'Championship' };

const DEFAULT_LAPS = 20;
const DEFAULT_MINUTES = 5;
const DEFAULT_RACES_PER_DRIVER = 3;
const DEFAULT_MAX_SIT_OUTS = 2;
const DEFAULT_YELLOW_GRACE_SECONDS = 5;
const DEFAULT_YELLOW_LAP_PENALTY_LAPS = 1;
const DEFAULT_POINTS = '10, 8, 6, 4, 3, 2';

function parsePoints(str) {
    if (!str) return '';
    try {
        const parsed = JSON.parse(str);
        return Array.isArray(parsed) ? parsed.join(', ') : str;
    } catch {
        return str;
    }
}

function serializePoints(str) {
    if (!str || !str.trim()) return null;
    const nums = str.split(',').map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n));
    return JSON.stringify(nums);
}

export default function SessionForm({ initial, meetingId, onSave, onCancel, hasPowerControl, previousYellowGraceSeconds }) {
    const [form, setForm] = useState(() => ({
        session_type: initial?.session_type ?? 'Points',
        end_condition_info: initial?.end_condition_info ?? DEFAULT_LAPS,
        races_per_driver: initial?.races_per_driver ?? DEFAULT_RACES_PER_DRIVER,
        max_sit_outs: initial?.max_sit_outs ?? DEFAULT_MAX_SIT_OUTS,
        // A new session starts from the meeting's previous session's value, else the default.
        yellow_grace_seconds: initial?.yellow_grace_seconds ?? previousYellowGraceSeconds ?? DEFAULT_YELLOW_GRACE_SECONDS,
        yellow_grace_power_pct: initial?.yellow_grace_power_pct ?? 100,
        yellow_post_grace_power_pct: initial?.yellow_post_grace_power_pct ?? 0,
        yellow_lap_penalty_laps: initial?.yellow_lap_penalty_laps ?? DEFAULT_YELLOW_LAP_PENALTY_LAPS,
        start_grid: initial?.start_grid ?? 'BehindLine',
        scoring_points: initial ? parsePoints(initial.scoring_points) : DEFAULT_POINTS,
    }));
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);

    const set = (field, value) => setForm(f => ({ ...f, [field]: value }));

    const isFastestLap = form.session_type === 'FastestLap';
    // Null means no sit-out limit — the "Sit-out penalty" toggle is just a friendlier
    // face on that same nullability, rather than a separate field.
    const sitOutPenaltyEnabled = form.max_sit_outs != null;
    const handleSitOutPenaltyToggle = (checked) => {
        set('max_sit_outs', checked ? (initial?.max_sit_outs ?? DEFAULT_MAX_SIT_OUTS) : null);
    };

    const handleSessionTypeChange = (newType) => {
        setForm(f => ({
            ...f,
            session_type: newType,
            end_condition_info: newType === 'FastestLap' ? DEFAULT_MINUTES : DEFAULT_LAPS,
        }));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setSaving(true);
        setError(null);
        const payload = {
            meeting_id: meetingId,
            session_type: form.session_type,
            // 'Laps' for Finishing Position races, 'Time' for Fastest Lap races.
            end_condition: isFastestLap ? 'Time' : 'Laps',
            end_condition_info: form.end_condition_info || null,
            races_per_driver: form.races_per_driver || null,
            max_sit_outs: form.max_sit_outs || null,
            yellow_grace_seconds: form.yellow_grace_seconds || DEFAULT_YELLOW_GRACE_SECONDS,
            // Locked server-side-safe regardless of what's in React state — the power
            // fields are hidden rather than cleared when there's no power control, so
            // stale form state could still carry a value, and the running Layer 1 could
            // in principle change between opening this form and saving it. Without power
            // control, the percentages can only ever be 100 (nothing can enforce less),
            // and the lap penalty is Finishing Position sessions only.
            yellow_grace_power_pct: hasPowerControl ? (form.yellow_grace_power_pct ?? 100) : 100,
            yellow_post_grace_power_pct: hasPowerControl ? (form.yellow_post_grace_power_pct ?? 0) : 100,
            yellow_lap_penalty_laps: (!hasPowerControl && !isFastestLap)
                ? (form.yellow_lap_penalty_laps || DEFAULT_YELLOW_LAP_PENALTY_LAPS) : 0,
            start_grid: form.start_grid,
            scoring_method: isFastestLap ? 'FastestLap' : 'PositionPoints',
            scoring_points: isFastestLap ? null : serializePoints(form.scoring_points),
        };
        try {
            await onSave(payload);
        } catch (err) {
            setError(err.message);
            setSaving(false);
        }
    };

    return (
        <form className="admin-form admin-session-form" onSubmit={handleSubmit}>
            <div className="admin-form-row">
                <label>Race type</label>
                <select value={form.session_type} onChange={e => handleSessionTypeChange(e.target.value)}>
                    {RACE_TYPES.map(t => <option key={t} value={t}>{SESSION_TYPE_LABELS[t]}</option>)}
                </select>
            </div>
            <div className="admin-form-row">
                <label>{isFastestLap ? 'Duration' : 'Race laps'}</label>
                <div className="admin-form-inline-value">
                    <input
                        className="admin-input-narrow"
                        type="number"
                        value={form.end_condition_info || ''}
                        onChange={e => set('end_condition_info', parseInt(e.target.value) || null)}
                        min="1"
                    />
                    <span className="admin-form-unit">{isFastestLap ? 'min' : 'laps'}</span>
                </div>
            </div>
            {!isFastestLap && (
                <div className="admin-form-row">
                    <label>Points scoring</label>
                    <input
                        value={form.scoring_points || ''}
                        onChange={e => set('scoring_points', e.target.value)}
                        placeholder={DEFAULT_POINTS}
                    />
                </div>
            )}
            <div className="admin-form-row">
                <label>Races per driver</label>
                <input
                    className="admin-input-narrow"
                    type="number"
                    value={form.races_per_driver || ''}
                    onChange={e => set('races_per_driver', parseInt(e.target.value) || null)}
                    min="1"
                />
            </div>
            <div className="admin-form-row">
                <label>Sit-out penalty</label>
                <label className="admin-toggle">
                    <input
                        type="checkbox"
                        checked={sitOutPenaltyEnabled}
                        onChange={e => handleSitOutPenaltyToggle(e.target.checked)}
                    />
                    <span className="admin-toggle-track"><span className="admin-toggle-thumb" /></span>
                </label>
            </div>
            {sitOutPenaltyEnabled && (
                <div className="admin-form-field-group">
                    <div className="admin-form-row">
                        <label>Max sit-outs</label>
                        <input
                            className="admin-input-narrow"
                            type="number"
                            value={form.max_sit_outs || ''}
                            onChange={e => set('max_sit_outs', parseInt(e.target.value) || null)}
                            min="1"
                        />
                    </div>
                    <p className="admin-form-hint">Driver is disqualified from the session after this many sit-outs.</p>
                </div>
            )}
            <div className="admin-form-row">
                <label>Start grid</label>
                <select value={form.start_grid} onChange={e => set('start_grid', e.target.value)}>
                    <option value="BehindLine">Behind the finish line</option>
                    <option value="InFrontOfLine">In front of the finish line</option>
                </select>
            </div>
            <div className="admin-form-section">
                <h4 className="admin-form-section-title">Yellow Flag</h4>
                <div className="admin-form-row">
                    <label>Grace period</label>
                    <div className="admin-form-inline-value">
                        <input
                            className="admin-input-narrow"
                            type="number"
                            value={form.yellow_grace_seconds || ''}
                            onChange={e => set('yellow_grace_seconds', parseInt(e.target.value) || null)}
                            min="1"
                        />
                        <span className="admin-form-unit">s</span>
                    </div>
                </div>
                {hasPowerControl && (
                    <>
                        <div className="admin-form-row">
                            <label>Max power during grace</label>
                            <div className="admin-form-inline-value">
                                <input
                                    className="admin-input-narrow"
                                    type="number"
                                    value={form.yellow_grace_power_pct ?? ''}
                                    onChange={e => set('yellow_grace_power_pct', parseInt(e.target.value) || 0)}
                                    min="0"
                                    max="100"
                                />
                                <span className="admin-form-unit">%</span>
                            </div>
                        </div>
                        <div className="admin-form-row">
                            <label>Max power after grace</label>
                            <div className="admin-form-inline-value">
                                <input
                                    className="admin-input-narrow"
                                    type="number"
                                    value={form.yellow_post_grace_power_pct ?? ''}
                                    onChange={e => set('yellow_post_grace_power_pct', parseInt(e.target.value) || 0)}
                                    min="0"
                                    max="100"
                                />
                                <span className="admin-form-unit">%</span>
                            </div>
                        </div>
                    </>
                )}
                {!hasPowerControl && !isFastestLap && (
                    <div className="admin-form-field-group">
                        <div className="admin-form-row">
                            <label>Penalty</label>
                            <div className="admin-form-inline-value">
                                <input
                                    className="admin-input-narrow"
                                    type="number"
                                    value={form.yellow_lap_penalty_laps || ''}
                                    onChange={e => set('yellow_lap_penalty_laps', parseInt(e.target.value) || null)}
                                    min="1"
                                />
                                <span className="admin-form-unit">laps</span>
                            </div>
                        </div>
                        <p className="admin-form-hint">Added to a driver&apos;s lap count for crossing the line after the grace period expires.</p>
                    </div>
                )}
            </div>
            {error && <p className="admin-error">{error}</p>}
            <div className="admin-form-actions">
                <button type="button" className="admin-btn-ghost" onClick={onCancel}>Cancel</button>
                <button type="submit" className="admin-btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
            </div>
        </form>
    );
}
