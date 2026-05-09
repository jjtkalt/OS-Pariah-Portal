-- 006_ban_data_collection.sql
-- Adds a ban evidence snapshot field and a related-accounts link table.

ALTER TABLE bans_master
  ADD COLUMN notes MEDIUMTEXT NULL;

CREATE TABLE IF NOT EXISTS `bans_related_uuid` (
  `banid` int(10) unsigned NOT NULL,
  `uuid` char(36) NOT NULL,
  `grid` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`banid`,`uuid`),
  CONSTRAINT `fk_bans_related_uuid` FOREIGN KEY (`banid`) REFERENCES `bans_master` (`banid`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

