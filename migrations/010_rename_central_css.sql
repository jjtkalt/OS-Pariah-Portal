-- Migration 010_rename_central_css.sql
-- PlatformStandards ADR-003: the primary stylesheet was renamed central.css -> base.css.
-- Repoint any stored custom_css_path that still references the old default filename so the
-- portal keeps serving a valid stylesheet after upgrade. Custom themes (any other value)
-- are left untouched.
UPDATE `config`
   SET `config_value` = '/static/css/base.css'
 WHERE `config_key` = 'custom_css_path'
   AND `config_value` = '/static/css/central.css';
