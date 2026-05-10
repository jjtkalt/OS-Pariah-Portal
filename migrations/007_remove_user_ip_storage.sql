-- Drop Gatekeeper IP ingestion storage, IP ban vectors, and client IP columns on audit/tickets.
-- Existing bans typed as 'ip' become 'mixed' so enum migration succeeds.

UPDATE bans_master SET type = 'mixed' WHERE type = 'ip';

DROP TABLE IF EXISTS bans_ip;
DROP TABLE IF EXISTS gatekeeper_ip;

ALTER TABLE bans_master
  MODIFY COLUMN `type` ENUM('account','mac','hostid','uuid','mixed') NOT NULL DEFAULT 'account';

ALTER TABLE audit_log DROP COLUMN IF EXISTS ip_address;

ALTER TABLE tickets DROP COLUMN IF EXISTS guest_ip;

DELETE FROM config WHERE config_key = 'ban_level_ip';
