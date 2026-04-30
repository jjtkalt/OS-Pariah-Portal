# app/utils/schema.py

KNOWN_SETTINGS = {
    "Grid Identity": {
        "grid_name": {"label": "Grid Name", "type": "text", "default": "OS Pariah", "no_reset": True},
        "grid_website_url": {"label": "Grid Main Website URL", "type": "url", "default": "https://example.com", "no_reset": True},
        "grid_domain": {"label": "Grid Base Domain (e.g., example.com)", "type": "text", "default": "ospariah.local", "no_reset": True},
        "portal_subdomain": {"label": "Portal Subdomain (e.g., portal)", "type": "text", "default": "portal", "no_reset": True},
        "robust_protocol": {"label": "Robust Protocol", "type": "text", "default": "http"},
        "robust_subdomain": {"label": "Robust Subdomain", "type": "text", "default": "robust"},
        "robust_public_port": {"label": "Robust Public Port", "type": "number", "default": "8002"},
        "robust_private_port": {"label": "Robust Private Port", "type": "number", "default": "8003"},
        "custom_css_path": {"label": "Custom CSS Path (For Theming)", "type": "text", "default": "/static/css/central.css"},
    },
    "Registration & Captcha": {
        "require_admin_approval": {"label": "Require Admin Approval for New Accounts", "type": "boolean", "default": "true"},
        "require_other_info": {"label": "Require 'Other Info' Essay", "type": "boolean", "default": "true"},
        "require_invite_code": {"label": "Require Invite Code", "type": "boolean", "default": "false"},
        "TURNSTILE_SITE_KEY": {"label": "Turnstile Site Key", "type": "text", "default": "3x00000000000000000000FF"},
        "TURNSTILE_SECRET_KEY": {"label": "Turnstile Secret Key", "type": "password", "default": "1x0000000000000000000000000000000AA"},
    },
    "User Access & Policies": {
        "global_policy_version": {"label": "Global Policy Version", "type": "text", "default": "0.0", "no_reset": True},
        "rejected_user_level": {"label": "Rejected User Level", "type": "number", "default": "-5"},
        "ban_level_account": {"label": "Account Ban User Level", "type": "number", "default": "-10"},
        "ban_level_ip": {"label": "IP Ban User Level", "type": "number", "default": "-11"},
        "ban_level_mac": {"label": "MAC Ban User Level", "type": "number", "default": "-12"},
        "ban_level_host": {"label": "HostID Ban User Level", "type": "number", "default": "-13"},
    },
    "Communications (Webhooks & Email)": {
        "discord_webhook_url": {"label": "Discord Webhook URL", "type": "password", "default": "", "no_reset": True},
        "matrix_webhook_url": {"label": "Matrix Server Base URL", "type": "url", "default": "", "no_reset": True},
        "matrix_access_token": {"label": "Matrix Access Token", "type": "password", "default": "", "no_reset": True},
        "matrix_room_id": {"label": "Matrix Room ID", "type": "text", "default": "", "no_reset": True},
        "smtp_server": {"label": "SMTP Server", "type": "text", "default": "", "no_reset": True},
        "smtp_port": {"label": "SMTP Port", "type": "number", "default": "587", "no_reset": True},
        "smtp_user": {"label": "SMTP Username", "type": "text", "default": "", "no_reset": True},
        "smtp_pass": {"label": "SMTP Password", "type": "password", "default": "", "no_reset": True},
        "smtp_from": {"label": "SMTP From Address", "type": "email", "default": "noreply@example.com"},
    },
    "Helpdesk & Support": {
        "allow_ticket_deletion": {"label": "Allow High Admins to Delete Tickets", "type": "boolean", "default": "false"},
        "allowed_attachment_exts": {"label": "Allowed Attachment Extensions", "type": "text", "default": "png,jpg,jpeg,gif,txt,pdf,log"},
    },
    "Region & Grid Defaults": {
        "default_max_agents": {"label": "Default Max Agents per Region", "type": "number", "default": "100"},
        "max_region_size_multiplier": {"label": "Max Region Size Multiplier", "type": "number", "default": "4"},
        "listable_regions": {"label": "Publicly Listable Regions", "type": "text", "default": "Welcome, Sandbox"},
        "region_host_ips": {"label": "Valid Region Host IPs (eg: 127.0.0.1, 192.168.1.50)", "type": "text", "default": "", "no_reset": True},
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

# --- RBAC BITWISE CONSTANTS ---
PERM_NONE             = 0
PERM_SUPER_ADMIN      = 1 << 0
PERM_MANAGE_ROLES     = 1 << 1
PERM_ADD_NOTES        = 1 << 2
PERM_VIEW_NOTES       = 1 << 3
PERM_STAFF_TICKETS    = 1 << 4
PERM_POST_NEWS        = 1 << 5
PERM_DELETE_NEWS      = 1 << 6
PERM_REGION_CONTROL   = 1 << 7
PERM_MANAGE_REGIONS   = 1 << 8
PERM_USER_LOOKUP      = 1 << 9
PERM_VIEW_ASSETS      = 1 << 10
PERM_MANAGE_SETTINGS  = 1 << 11
PERM_MANAGE_INFRA     = 1 << 12
PERM_ISSUE_BANS       = 1 << 13
PERM_APPROVE_USERS    = 1 << 14
PERM_RENAME_USERS     = 1 << 15
PERM_DELETE_TICKETS   = 1 << 16
PERM_DELETE_USER      = 1 << 17
PERM_MANAGE_ASSETS    = 1 << 18
PERM_MANAGE_POLICIES  = 1 << 19 # Legal/Grid Rules
PERM_UPDATE_EMAIL     = 1 << 20 # 1048576 - Admin: Force update user emails
PERM_FORCE_PWRESET    = 1 << 21 # 2097152 - Admin: Send password reset links
PERM_VIEW_AUDIT       = 1 << 22 # 4194304 - Security: View Audit Logs
PERM_MANAGE_GUIDES    = 1 << 23 # Viewer Setup / Technical
PERM_MANAGE_RESOURCES = 1 << 24 # Creator / Member resources
PERM_VIEW_PPI         = 1 << 25 # View Users's PII

# --- UNIFIED RBAC UI SCHEMA ---
RBAC_SCHEMA = {
    "System & Security": {
        PERM_MANAGE_ROLES: {"label": "Manage Roles", "desc": "Can modify user permissions", "super_only": True},
        PERM_MANAGE_INFRA: {"label": "Manage Infra", "desc": "Modify DNS/Host Mappings", "super_only": True},
        PERM_VIEW_AUDIT: {"label": "View Audit Logs", "desc": "Access the administrative action tracking log", "super_only": True},
        PERM_MANAGE_SETTINGS: {"label": "Manage Settings", "desc": "Edit global configurations", "super_only": True},
        PERM_SUPER_ADMIN: {"label": "Super Admin", "desc": "Master Key: Overrides all checks", "super_only": True},
    },
    "Grid Operations": {
        PERM_REGION_CONTROL: {"label": "Region Control", "desc": "Start/Stop/Restart/OAR regions"},
        PERM_MANAGE_REGIONS: {"label": "Manage Regions", "desc": "Edit WebXML configs & limits", "super_only": True},
    },
    "Moderation & Support": {
        PERM_STAFF_TICKETS: {"label": "Helpdesk Access", "desc": "View, assign, and reply to tickets"},
        PERM_USER_LOOKUP: {"label": "Gatekeeper Lookup", "desc": "Search alt-accounts via IP/MAC"},
        PERM_VIEW_NOTES: {"label": "View Staff Notes", "desc": "Read internal warnings"},
        PERM_ADD_NOTES: {"label": "Add Staff Notes", "desc": "Attach internal warnings to users"},
        PERM_VIEW_PPI: {"label": "View USE PPI", "desc": "View user's connection Protected Personal Information", "super_only": True},
        PERM_ISSUE_BANS: {"label": "Issue Bans", "desc": "Create/Remove active grid bans", "super_only": True},
        PERM_DELETE_TICKETS: {"label": "Delete Tickets", "desc": "Permanently erase tickets", "super_only": True},
    },
    "User Administration": {
        PERM_APPROVE_USERS: {"label": "Approve Registrations", "desc": "Review and approve new users", "super_only": True},
        PERM_FORCE_PWRESET: {"label": "Force Password Reset", "desc": "Dispatch a secure reset link to a user"},
        PERM_UPDATE_EMAIL: {"label": "Update Emails", "desc": "Force update a user's contact email"},
        PERM_RENAME_USERS: {"label": "Rename Avatars", "desc": "Change first and last names", "super_only": True},
        PERM_DELETE_USER: {"label": "Delete User", "desc": "Erase avatar from the grid", "super_only": True},
    },
    "Communications & Assets": {
        PERM_MANAGE_GUIDES: {"label": "Manage Guides", "desc": "Edit Viewer Setup & Technical Guides"},
        PERM_MANAGE_RESOURCES: {"label": "Manage Resource Documents", "desc": "Edit Creator & Member Resources"},
        PERM_POST_NEWS: {"label": "Post News", "desc": "Publish grid announcements"},
        PERM_DELETE_NEWS: {"label": "Delete News", "desc": "Remove grid announcements"},
        PERM_VIEW_ASSETS: {"label": "View Assets", "desc": "Access texture gallery", "super_only": True},
        PERM_MANAGE_POLICIES: {"label": "Manage Policies", "desc": "Edit Legal Grid Policies & Rules", "super_only": True},
        PERM_MANAGE_ASSETS: {"label": "Manage Assets", "desc": "Purge items from FSAssets", "super_only": True},
    }
}