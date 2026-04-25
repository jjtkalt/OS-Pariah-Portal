-- Migration 003_add_rbac_table.sql
CREATE TABLE IF NOT EXISTS `user_rbac` (
  `user_uuid` CHAR(36) PRIMARY KEY,
  `permissions` BIGINT UNSIGNED DEFAULT 0,
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT `fk_rbac_uuid` FOREIGN KEY (`user_uuid`) REFERENCES `pending_registrations` (`user_uuid`) ON DELETE CASCADE
) ENGINE=InnoDB;