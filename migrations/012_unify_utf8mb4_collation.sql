-- Unify os_pariah string collations.
--
-- Leap 16 / MariaDB 11+ often defaults new databases to utf8mb4_uca1400_ai_ci.
-- Migration 001 tables were created with utf8mb4_general_ci; later migrations
-- (e.g. 008 calendar) used DEFAULT CHARSET=utf8mb4 without COLLATE and inherited
-- the database default. JOINs such as calendar_events.region_uuid = region_configs.region_uuid
-- then fail with:
--   Illegal mix of collations (utf8mb4_uca1400_ai_ci,IMPLICIT) and
--   (utf8mb4_general_ci,IMPLICIT) for operation '='
--
-- Canonical collation matches docs/DEPLOYMENT.md: utf8mb4_unicode_ci.
-- DROP foreign keys first — CONVERT TO cannot rewrite referenced PK/FK columns.

ALTER DATABASE CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

ALTER TABLE `bans_host_id` DROP FOREIGN KEY `fk_bans_host`;
ALTER TABLE `bans_mac` DROP FOREIGN KEY `fk_bans_mac`;
ALTER TABLE `bans_username` DROP FOREIGN KEY `fk_bans_username`;
ALTER TABLE `bans_uuid` DROP FOREIGN KEY `fk_bans_uuid`;
ALTER TABLE `bans_related_uuid` DROP FOREIGN KEY `fk_bans_related_uuid`;
ALTER TABLE `region_settings` DROP FOREIGN KEY `fk_region_settings`;
ALTER TABLE `ticket_replies` DROP FOREIGN KEY `fk_ticket_reply`;

ALTER TABLE `audit_log` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `bans_host_id` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `bans_mac` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `bans_master` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `bans_related_uuid` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `bans_username` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `bans_uuid` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `bot_message_queue` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `calendar_events` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `config` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `event_feed_subscriptions` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `event_follows` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `event_notification_log` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `event_suggestions` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `gatekeeper_from` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `gatekeeper_host_id` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `gatekeeper_mac` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `global_news` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `iar_backups` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `oidc_access_tokens` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `oidc_auth_codes` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `oidc_clients` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `password_resets` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `pending_registrations` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `policies` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `policy_agreements` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `region_configs` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `region_hosts` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `region_settings` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `schema_versions` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `texture_gallery_snapshot` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `ticket_attachments` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `ticket_replies` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `tickets` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `user_notes` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `user_notices` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `user_rbac` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

ALTER TABLE `bans_host_id`
  ADD CONSTRAINT `fk_bans_host` FOREIGN KEY (`banid`) REFERENCES `bans_master` (`banid`) ON DELETE CASCADE;
ALTER TABLE `bans_mac`
  ADD CONSTRAINT `fk_bans_mac` FOREIGN KEY (`banid`) REFERENCES `bans_master` (`banid`) ON DELETE CASCADE;
ALTER TABLE `bans_username`
  ADD CONSTRAINT `fk_bans_username` FOREIGN KEY (`banid`) REFERENCES `bans_master` (`banid`) ON DELETE CASCADE;
ALTER TABLE `bans_uuid`
  ADD CONSTRAINT `fk_bans_uuid` FOREIGN KEY (`banid`) REFERENCES `bans_master` (`banid`) ON DELETE CASCADE;
ALTER TABLE `bans_related_uuid`
  ADD CONSTRAINT `fk_bans_related_uuid` FOREIGN KEY (`banid`) REFERENCES `bans_master` (`banid`) ON DELETE CASCADE;
ALTER TABLE `region_settings`
  ADD CONSTRAINT `fk_region_settings` FOREIGN KEY (`region_uuid`) REFERENCES `region_configs` (`region_uuid`) ON DELETE CASCADE;
ALTER TABLE `ticket_replies`
  ADD CONSTRAINT `fk_ticket_reply` FOREIGN KEY (`ticket_id`) REFERENCES `tickets` (`id`) ON DELETE CASCADE;
