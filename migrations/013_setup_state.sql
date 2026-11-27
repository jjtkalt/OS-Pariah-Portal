-- Migration 013_setup_state.sql
-- First-boot / setup wizard state (docs/ROADMAP.md, issue #25).
--
-- One row per wizard step (step_id matches app/setup/steps.py), plus one reserved
-- bookkeeping row `_install` describing the install itself (origin fresh|upgraded,
-- instance id, grid provider, whether first-boot is complete). Rows are created and
-- reconciled by scripts/migrate.py (app.setup.state.reconcile), not by this file, so
-- the step list can grow in later releases without new migrations.
--
-- Explicit collation: migration 012 unified the portal DB on utf8mb4_unicode_ci; new
-- tables must not fall back to a server default that can reintroduce collation mixes.
CREATE TABLE IF NOT EXISTS `setup_state` (
    `step_id` VARCHAR(64) NOT NULL,
    `step_version` INT NOT NULL DEFAULT 1,
    `status` ENUM('pending', 'done', 'skipped') NOT NULL DEFAULT 'pending',
    `detail` TEXT NULL,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`step_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
