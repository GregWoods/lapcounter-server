-- 007: meetings.public_id — an unguessable id for guest-facing URLs (/m/<public_id>/...).
--
-- Guests reach a meeting through a link or QR code containing this id instead of the
-- sequential integer id, so one customer's drivers can't wander into another customer's
-- meeting by trying /m/1, /m/2... It is obscurity, not authentication: it only stops
-- drivers peeking at each other's names.
--
-- gen_random_uuid() is built in from PostgreSQL 13 (the stack runs 17). Adding the
-- column with a volatile default fills every existing row with its own value. Re-running
-- is safe.
--
-- Apply:
--   docker exec -i database psql -U lap -d lapcounter_server < database/migrations/007-meetings-public-id.sql
--
-- ⚠️ The new API selects meetings.public_id, so deploy the migration and the API together.

ALTER TABLE meetings ADD COLUMN IF NOT EXISTS public_id UUID NOT NULL DEFAULT gen_random_uuid();
CREATE UNIQUE INDEX IF NOT EXISTS meetings_public_id_key ON meetings (public_id);
