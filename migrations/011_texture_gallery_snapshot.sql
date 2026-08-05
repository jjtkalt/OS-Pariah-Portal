-- Migration 011_texture_gallery_snapshot.sql
-- Denormalized recent-texture listing for /admin/gallery so request path
-- does not run the heavy Robust inventoryitems ⨝ fsassets join.
CREATE TABLE IF NOT EXISTS `texture_gallery_snapshot` (
    `hash` VARCHAR(128) NOT NULL,
    `asset_id` VARCHAR(36) NOT NULL,
    `name` VARCHAR(255) NULL,
    `create_time` INT UNSIGNED NOT NULL DEFAULT 0,
    `owner_uuid` VARCHAR(36) NULL,
    `owner_name` VARCHAR(255) NULL,
    `refreshed_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`hash`),
    KEY `idx_tg_snap_create` (`create_time`),
    KEY `idx_tg_snap_owner_create` (`owner_uuid`, `create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
