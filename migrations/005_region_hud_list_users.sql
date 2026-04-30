-- Public HUD: only regions with hud_list_users=1 appear in /api/online for non-admin callers.
-- Default 0 = Users Unlisted (not shown on public HUD).

ALTER TABLE `region_configs`
ADD COLUMN `hud_list_users` TINYINT(1) NOT NULL DEFAULT 0
AFTER `is_active`;

-- Delete any existing listable_regions setting from the config table so we don't have legacy logic that is no longer needed.
DELETE FROM config WHERE config_key = 'listable_regions';