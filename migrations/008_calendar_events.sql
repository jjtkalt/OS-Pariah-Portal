-- Calendar / events system

CREATE TABLE IF NOT EXISTS `calendar_events` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `title` VARCHAR(255) NOT NULL,
  `description` TEXT NULL,
  `starts_at` DATETIME NOT NULL,
  `ends_at` DATETIME NULL,
  `all_day` TINYINT(1) NOT NULL DEFAULT 0,
  `location` VARCHAR(512) NULL,
  `slurl` VARCHAR(512) NULL,
  `region_uuid` CHAR(36) NULL,
  `organizer_uuid` CHAR(36) NULL,
  `event_tier` ENUM('official','community','region','organizer') NOT NULL DEFAULT 'community',
  `category` ENUM('maintenance','social','class','competition','other') NOT NULL DEFAULT 'other',
  `status` ENUM('draft','published','cancelled') NOT NULL DEFAULT 'draft',
  `recurrence_rule` VARCHAR(512) NULL,
  `recurrence_until` DATETIME NULL,
  `recurrence_parent_id` INT UNSIGNED NULL,
  `recurrence_exception_dates` JSON NULL,
  `cancelled_occurrences` JSON NULL,
  `source_suggestion_id` INT UNSIGNED NULL,
  `created_by_uuid` CHAR(36) NOT NULL,
  `created_by_name` VARCHAR(128) NOT NULL,
  `published_at` DATETIME NULL,
  `updated_at` DATETIME NULL ON UPDATE CURRENT_TIMESTAMP,
  `cancelled_at` DATETIME NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_calendar_events_status_starts` (`status`, `starts_at`),
  KEY `idx_calendar_events_tier_starts` (`event_tier`, `starts_at`),
  KEY `idx_calendar_events_region` (`region_uuid`, `starts_at`),
  KEY `idx_calendar_events_parent` (`recurrence_parent_id`),
  FULLTEXT KEY `ft_calendar_events_search` (`title`, `description`, `location`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `event_suggestions` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `submitter_uuid` CHAR(36) NOT NULL,
  `submitter_name` VARCHAR(128) NOT NULL,
  `title` VARCHAR(255) NOT NULL,
  `description` TEXT NULL,
  `starts_at` DATETIME NOT NULL,
  `ends_at` DATETIME NULL,
  `all_day` TINYINT(1) NOT NULL DEFAULT 0,
  `location` VARCHAR(512) NULL,
  `slurl` VARCHAR(512) NULL,
  `region_uuid` CHAR(36) NULL,
  `event_tier` ENUM('official','community','region','organizer') NOT NULL DEFAULT 'organizer',
  `category` ENUM('maintenance','social','class','competition','other') NOT NULL DEFAULT 'other',
  `recurrence_rule` VARCHAR(512) NULL,
  `recurrence_until` DATETIME NULL,
  `status` ENUM('pending','approved','rejected','withdrawn') NOT NULL DEFAULT 'pending',
  `staff_notes` TEXT NULL,
  `reviewed_by_uuid` CHAR(36) NULL,
  `reviewed_at` DATETIME NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_event_suggestions_status` (`status`, `created_at`),
  KEY `idx_event_suggestions_submitter` (`submitter_uuid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `event_follows` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `user_uuid` CHAR(36) NOT NULL,
  `event_id` INT UNSIGNED NOT NULL,
  `notify_email` TINYINT(1) NOT NULL DEFAULT 1,
  `notify_inworld` TINYINT(1) NOT NULL DEFAULT 1,
  `reminder_offsets` JSON NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_event_follows_user_event` (`user_uuid`, `event_id`),
  KEY `idx_event_follows_event` (`event_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `event_feed_subscriptions` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `user_uuid` CHAR(36) NULL,
  `subscription_token` CHAR(36) NOT NULL,
  `filter_tiers` JSON NULL,
  `filter_categories` JSON NULL,
  `filter_regions` JSON NULL,
  `feed_format` ENUM('ics','rss') NOT NULL DEFAULT 'ics',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_event_feed_sub_token` (`subscription_token`),
  KEY `idx_event_feed_sub_user` (`user_uuid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `bot_message_queue` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `source` VARCHAR(64) NOT NULL,
  `message_type` VARCHAR(64) NOT NULL,
  `target_uuid` CHAR(36) NULL,
  `target_region_uuid` CHAR(36) NULL,
  `message_body` TEXT NOT NULL,
  `priority` ENUM('normal','high') NOT NULL DEFAULT 'normal',
  `status` ENUM('pending','claimed','delivered','failed') NOT NULL DEFAULT 'pending',
  `claimed_at` DATETIME NULL,
  `delivered_at` DATETIME NULL,
  `retry_count` INT UNSIGNED NOT NULL DEFAULT 0,
  `last_error` VARCHAR(512) NULL,
  `metadata` JSON NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_bot_queue_status_priority` (`status`, `priority`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `event_notification_log` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `event_id` INT UNSIGNED NOT NULL,
  `user_uuid` CHAR(36) NULL,
  `occurrence_start` DATETIME NOT NULL,
  `notification_type` VARCHAR(64) NOT NULL,
  `sent_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_event_notification_dedup` (`event_id`, `user_uuid`, `occurrence_start`, `notification_type`),
  KEY `idx_event_notification_event` (`event_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
