# app/utils/schema.py

KNOWN_SETTINGS = {
    "Grid Identity": {
        "grid_name": {"label": "Grid Name", "type": "text", "default": "OS Pariah"},
        "DOMAIN": {"label": "Robust Domain (Base URL)", "type": "url", "default": "https://world.example.com"},
        "portal_url": {"label": "Portal Domain URL", "type": "url", "default": "https://portal.example.com"},
        "grid_website_url": {"label": "Grid Main Website URL", "type": "url", "default": "https://example.com"},
    },
    "Registration & Captcha": {
        "require_admin_approval": {"label": "Require Admin Approval for New Accounts", "type": "boolean", "default": "true"},
        "require_other_info": {"label": "Require 'Other Info' Essay", "type": "boolean", "default": "true"},
        "require_invite_code": {"label": "Require Invite Code", "type": "boolean", "default": "false"},
        "TURNSTILE_SITE_KEY": {"label": "Turnstile Site Key", "type": "text", "default": "3x00000000000000000000FF"},
        "TURNSTILE_SECRET_KEY": {"label": "Turnstile Secret Key", "type": "password", "default": "1x0000000000000000000000000000000AA"},
    },
    "User Access & Policies": {
        "global_policy_version": {"label": "Global Policy Version", "type": "text", "default": "1.0"},
        "rejected_user_level": {"label": "Rejected User Level", "type": "number", "default": "-5"},
        "ban_level_account": {"label": "Account Ban User Level", "type": "number", "default": "-10"},
        "ban_level_ip": {"label": "IP Ban User Level", "type": "number", "default": "-11"},
        "ban_level_mac": {"label": "MAC Ban User Level", "type": "number", "default": "-12"},
        "ban_level_host": {"label": "HostID Ban User Level", "type": "number", "default": "-13"},
    },
    "Communications (Webhooks & Email)": {
        "discord_webhook_url": {"label": "Discord Webhook URL", "type": "password", "default": ""},
        "matrix_webhook_url": {"label": "Matrix Server Base URL", "type": "url", "default": ""},
        "matrix_access_token": {"label": "Matrix Access Token", "type": "password", "default": ""},
        "matrix_room_id": {"label": "Matrix Room ID", "type": "text", "default": ""},
        "smtp_server": {"label": "SMTP Server", "type": "text", "default": ""},
        "smtp_port": {"label": "SMTP Port", "type": "number", "default": "587"},
        "smtp_user": {"label": "SMTP Username", "type": "text", "default": ""},
        "smtp_pass": {"label": "SMTP Password", "type": "password", "default": ""},
        "smtp_from": {"label": "SMTP From Address", "type": "email", "default": "noreply@example.com"},
    },
    "Helpdesk & Support": {
        "allow_ticket_deletion": {"label": "Allow Users to Delete Tickets", "type": "boolean", "default": "false"},
        "allowed_attachment_exts": {"label": "Allowed Attachment Extensions", "type": "text", "default": "png,jpg,jpeg,gif,txt,pdf,log"},
    },
    "Region & Grid Defaults": {
        "default_max_agents": {"label": "Default Max Agents per Region", "type": "number", "default": "100"},
        "max_region_size_multiplier": {"label": "Max Region Size Multiplier", "type": "number", "default": "4"},
        "listable_regions": {"label": "Publicly Listable Regions", "type": "text", "default": "Welcome, Sandbox"},
        "region_host_ips": {"label": "Allowed Region Host IPs", "type": "text", "default": ""},
    },
    "IAR & Backups": {
        "IAR_OUTPUT_DIR": {"label": "IAR Output Directory", "type": "text", "default": "/home/opensim/Backups/downloads/iars"},
        "IAR_REGION_SCREEN": {"label": "Region Screen For IAR Generation", "type": "text", "default": "OpenSim-Admin2"},
        "iar_retention_days": {"label": "IAR Retention (Days)", "type": "number", "default": "7"},
    },
    "System & Backend (Requires Restart)": {
        "CACHE_TYPE": {"label": "Cache Type", "type": "text", "default": "SimpleCache"},
        "CACHE_DEFAULT_TIMEOUT": {"label": "Cache Default Timeout (Seconds)", "type": "number", "default": "30"},
        "PERMANENT_SESSION_LIFETIME": {"label": "Session Lifetime (Seconds)", "type": "number", "default": "28800"},
        "fsassets_path": {"label": "FSAssets Directory Location", "type": "text", "default": "/home/opensim/FSAssets/data"},
        "texture_cache_path": {"label": "Cache Directory Location", "type": "text", "default": "/home/opensim/FSAssets/pariahcache"},
    }
}