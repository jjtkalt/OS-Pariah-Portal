CREATE TABLE IF NOT EXISTS `audit_log` (
    `id` INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `admin_uuid` CHAR(36) NOT NULL,
    `admin_name` VARCHAR(100) NOT NULL,
    `action` VARCHAR(100) NOT NULL,
    `target_uuid` CHAR(36) DEFAULT NULL,
    `details` TEXT NOT NULL,
    `ip_address` VARCHAR(45) NOT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;