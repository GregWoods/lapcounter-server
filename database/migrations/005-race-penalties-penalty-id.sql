-- One row per penalty (#94). driver_penalty is now delivered at least once (QoS 1, a
-- persistent dbwriter session, acked only after the commit), so the same penalty can
-- arrive twice; dbwriter inserts with ON CONFLICT (penalty_id) DO NOTHING.
--
-- Keyed on an id lapdata mints once when it applies the penalty, not on the crossing that
-- incurred it: a future penalty a marshal issues by hand has no crossing, and its NULL
-- clock would never match a unique key. An id is unique by design, whatever triggered it.
--
-- Rows from before #94 have no penalty_id; a unique constraint counts NULLs as distinct,
-- so it applies cleanly.

ALTER TABLE race_penalties
    -- The dedup key.
    ADD COLUMN penalty_id UUID,
    -- When lapdata gave the penalty, for people reading the table. created_at is when
    -- dbwriter wrote the row, which a redelivery can make much later.
    ADD COLUMN issued_at TIMESTAMPTZ,
    -- The crossing that incurred it, for traceability: the same pair its driver_laps row
    -- carries. NULL for a penalty with no crossing.
    ADD COLUMN clock VARCHAR(64),
    ADD COLUMN counter_ms BIGINT,
    ADD CONSTRAINT race_penalties_one_row_per_penalty UNIQUE (penalty_id);
