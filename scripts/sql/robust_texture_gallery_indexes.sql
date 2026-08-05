-- Additive indexes for OS Pariah Texture Gallery (Robust DB).
-- Safe for OpenSimulator / NGC-Tranquility: indexes only; no column or data changes.
-- Idempotent when applied via scripts/apply_robust_texture_indexes.py
--
-- Manual one-shot (as a MariaDB admin, NOT the portal robust_ro user):
--   sudo mariadb robust < /opt/os_pariah/scripts/sql/robust_texture_gallery_indexes.sql
--
-- Or:
--   sudo /opt/os_pariah/venv/bin/python /opt/os_pariah/scripts/apply_robust_texture_indexes.py

-- Newest-first fsassets scans for the inverted gallery / snapshot refresh query.
CREATE INDEX IF NOT EXISTS idx_pariah_fsassets_create_time
    ON fsassets (create_time);

-- Join inventoryitems -> fsassets by asset UUID.
CREATE INDEX IF NOT EXISTS idx_pariah_inventoryitems_assetid
    ON inventoryitems (assetID);

-- Per-user texture gallery filter (assetType=0 + avatarID).
CREATE INDEX IF NOT EXISTS idx_pariah_inventoryitems_type_avatar
    ON inventoryitems (assetType, avatarID);
