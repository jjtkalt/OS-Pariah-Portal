-- Calendar / bot queue enhancements (group delivery, event group flags)

ALTER TABLE `bot_message_queue`
  ADD COLUMN `delivery_channel` ENUM('im','region','group_chat','group_notice') NOT NULL DEFAULT 'region' AFTER `message_type`,
  ADD COLUMN `target_group_uuid` CHAR(36) NULL AFTER `target_region_uuid`,
  ADD COLUMN `notice_subject` VARCHAR(255) NULL AFTER `message_body`;

ALTER TABLE `calendar_events`
  ADD COLUMN `announce_group_uuid` CHAR(36) NULL AFTER `region_uuid`,
  ADD COLUMN `use_group_chat` TINYINT(1) NULL DEFAULT NULL COMMENT 'NULL=use grid default',
  ADD COLUMN `use_group_notice` TINYINT(1) NULL DEFAULT NULL COMMENT 'NULL=use grid default';
