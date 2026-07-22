import gzip
import io
import os
import re
import uuid

import cv2
import numpy as np
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)

from app.utils.audit import log_audit_action
from app.utils.auth_helpers import has_permission, rbac_required
from app.utils.db import get_dynamic_config, get_pariah_db, get_robust_db
from app.utils.notifications import (
    send_approval_email,
    send_matrix_discord_webhook,
    send_verification_email,
)
from app.utils.robust_api import set_user_level
from app.utils.schema import (
    KNOWN_SETTINGS,
    PERM_APPROVE_USERS,
    PERM_MANAGE_EVENTS,
    PERM_MANAGE_SETTINGS,
    PERM_VIEW_ASSETS,
    PERM_VIEW_AUDIT,
)
from app.utils.texture_gallery import (
    fetch_textures_from_snapshot,
    fetch_textures_inverted,
    snapshot_count,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/approvals", methods=["GET"])
@rbac_required(PERM_APPROVE_USERS)
def pending_approvals():
    """Renders the dashboard of users awaiting email verification or staff approval."""
    view = request.args.get("view", "approval")
    if view not in ("approval", "email"):
        view = "approval"

    status = "pending_email" if view == "email" else "pending_approval"
    pariah_conn = get_pariah_db()
    pending_users = []

    with pariah_conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT user_uuid, email, inviter, discord, matrix, other_info, created_at
            FROM pending_registrations
            WHERE status = %s
            ORDER BY created_at ASC
        """,
            (status,),
        )
        pending_records = cursor.fetchall()

    if pending_records:
        robust_conn = get_robust_db()
        uuids = [record["user_uuid"] for record in pending_records]
        format_strings = ",".join(["%s"] * len(uuids))
        user_names = {}

        try:
            with robust_conn.cursor() as r_cursor:
                r_cursor.execute(
                    f"SELECT PrincipalID, FirstName, LastName FROM useraccounts WHERE PrincipalID IN ({format_strings})",
                    tuple(uuids),
                )
                for row in r_cursor.fetchall():
                    user_names[row["PrincipalID"]] = {
                        "first_name": row["FirstName"],
                        "last_name": row["LastName"],
                    }
        except Exception as e:
            current_app.logger.error(f"Failed to fetch user names from Robust: {e}")

        for record in pending_records:
            user_uuid = record["user_uuid"]
            record["first_name"] = user_names.get(user_uuid, {}).get(
                "first_name", "Unknown"
            )
            record["last_name"] = user_names.get(user_uuid, {}).get("last_name", "User")
            pending_users.append(record)

    return render_template("admin/approvals.html", users=pending_users, view=view)


@admin_bp.route("/approvals/approve", methods=["POST"])
@rbac_required(PERM_APPROVE_USERS)
def approve_user():
    """AJAX endpoint to approve a user and grant Level 0 access."""
    uuid = request.form.get("uuid")
    email = request.form.get("email")

    if not uuid:
        return jsonify({"status": "error", "message": "Missing UUID."}), 400

    try:
        # ROBUST Call: setaccount
        if set_user_level(uuid, 0):
            # 2. Update Pariah DB state
            pariah_conn = get_pariah_db()
            with pariah_conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE pending_registrations SET status = 'approved' WHERE user_uuid = %s",
                    (uuid,),
                )
            pariah_conn.commit()
            log_audit_action("Approvals", "Approved new user", target_uuid=uuid)

            # 3. Asynchronous Notifications
            grid_name = get_dynamic_config("grid_name")
            send_approval_email(email, grid_name)

            send_matrix_discord_webhook(
                title="✅ Account Approved",
                message=f"A pending user ({uuid}) has been approved and set to Level 0.",
                color=3066993,  # Green
            )
            return jsonify({"status": "success"})
        else:
            return jsonify(
                {
                    "status": "error",
                    "message": "ROBUST API failed. Check if port 8003 is accessible.",
                }
            )
    except Exception:
        current_app.logger.exception("Approval exception")
        return jsonify(
            {
                "status": "error",
                "message": "An unexpected error occurred while approving the user.",
            }
        ), 500


@admin_bp.route("/approvals/resend-verification", methods=["POST"])
@rbac_required(PERM_APPROVE_USERS)
def resend_verification():
    """AJAX endpoint to rotate the verification token and resend the email."""
    user_uuid = request.form.get("uuid")

    if not user_uuid:
        return jsonify({"status": "error", "message": "Missing UUID."}), 400

    try:
        new_token = uuid.uuid4().hex
        pariah_conn = get_pariah_db()
        with pariah_conn.cursor() as cursor:
            cursor.execute(
                "UPDATE pending_registrations SET verification_token = %s WHERE user_uuid = %s AND status = 'pending_email'",
                (new_token, user_uuid),
            )
            if cursor.rowcount != 1:
                cursor.execute(
                    "SELECT status FROM pending_registrations WHERE user_uuid = %s",
                    (user_uuid,),
                )
                reg = cursor.fetchone()
                pariah_conn.rollback()
                if not reg:
                    return jsonify(
                        {"status": "error", "message": "Registration not found."}
                    ), 404
                return jsonify(
                    {
                        "status": "error",
                        "message": "This user is not awaiting email verification.",
                    }
                ), 400

            cursor.execute(
                "SELECT email FROM pending_registrations WHERE user_uuid = %s",
                (user_uuid,),
            )
            reg = cursor.fetchone()

        pariah_conn.commit()

        send_verification_email(reg["email"], new_token)
        log_audit_action(
            "Approvals", "Resent email verification link", target_uuid=user_uuid
        )

        return jsonify({"status": "success"})
    except Exception:
        current_app.logger.exception("Resend verification exception")
        return jsonify(
            {
                "status": "error",
                "message": "An unexpected error occurred while resending the verification email.",
            }
        ), 500


@admin_bp.route("/approvals/reject", methods=["POST"])
@rbac_required(PERM_APPROVE_USERS)
def reject_user():
    """AJAX endpoint to reject a user, leaving them locked out."""
    uuid = request.form.get("uuid")

    if not uuid:
        return jsonify({"status": "error", "message": "Missing UUID."}), 400

    try:
        # We will update this -5 logic in our next sweep to use the dynamic config!
        rejected_level = int(get_dynamic_config("rejected_user_level"))

        pariah_conn = get_pariah_db()
        with pariah_conn.cursor() as cursor:
            cursor.execute(
                "UPDATE pending_registrations SET status = 'rejected' WHERE user_uuid = %s",
                (uuid,),
            )
        pariah_conn.commit()
        log_audit_action("Approvals", "Rejected new user", target_uuid=uuid)

        set_user_level(uuid, rejected_level)

        return jsonify({"status": "success"})
    except Exception:
        current_app.logger.exception("Rejection exception")
        return jsonify(
            {
                "status": "error",
                "message": "An unexpected error occurred while rejecting the user.",
            }
        ), 500


@admin_bp.route("/settings", methods=["GET"])
@rbac_required(PERM_MANAGE_SETTINGS)
def system_settings():
    """Admin dashboard to configure dynamic portal settings."""
    pariah_conn = get_pariah_db()

    # Fetch existing DB settings
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT config_key, config_value FROM config")
        db_rows = cursor.fetchall()

    db_settings = {row["config_key"]: row["config_value"] for row in db_rows}
    known_keys = [k for cat in KNOWN_SETTINGS.values() for k in cat]
    custom_settings = {k: v for k, v in db_settings.items() if k not in known_keys}

    return render_template(
        "admin/settings.html",
        schema=KNOWN_SETTINGS,
        db_settings=db_settings,
        custom_settings=custom_settings,
    )


@admin_bp.route("/settings/update_single", methods=["POST"])
@rbac_required(PERM_MANAGE_SETTINGS)
def update_single_setting():
    """AJAX endpoint to update a single setting on the fly."""
    key = request.form.get("key")
    val = request.form.get("value", "").strip()

    if not key:
        return jsonify(
            {"status": "error", "message": "Missing configuration key."}
        ), 400

    # Strip the 'cfg_' prefix we use in the HTML IDs
    actual_key = key.replace("cfg_", "") if key.startswith("cfg_") else key

    meta = None
    for fields in KNOWN_SETTINGS.values():
        if actual_key in fields:
            meta = fields[actual_key]
            break

    is_default = meta is not None and str(meta.get("default", "")) == val

    if meta and meta.get("type") == "selectable":
        opts_raw = meta.get("options") or ""
        allowed = [x.strip() for x in opts_raw.split(",") if x.strip()]
        if allowed and val not in allowed:
            return jsonify(
                {"status": "error", "message": "Value is not allowed for this setting."}
            ), 400

    pariah_conn = get_pariah_db()
    try:
        with pariah_conn.cursor() as cursor:
            # If it is the default, DELETE it from the DB to keep things clean
            if is_default:
                cursor.execute(
                    "DELETE FROM config WHERE config_key = %s", (actual_key,)
                )
            else:
                # Otherwise, save the custom override
                cursor.execute(
                    """
                    INSERT INTO config (config_key, config_value, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON DUPLICATE KEY UPDATE config_value = VALUES(config_value), updated_at = CURRENT_TIMESTAMP
                """,
                    (actual_key, val),
                )
        pariah_conn.commit()
        log_audit_action("System Setting", f"Changed '{actual_key}' to '{val}'")
        return jsonify({"status": "success", "is_default": is_default})
    except Exception as e:
        current_app.logger.error(f"Failed to update config {actual_key}: {e}")
        return jsonify({"status": "error", "message": "Database error."}), 500


@admin_bp.route("/settings/add", methods=["POST"])
@rbac_required(PERM_MANAGE_SETTINGS)
def add_setting():
    """Injects a new custom override key into the configuration table."""

    new_key = request.form.get("new_key", "").strip()
    new_value = request.form.get("new_value", "").strip()

    if new_key and new_value:
        try:
            conn = get_pariah_db()
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO config (config_key, config_value)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE config_value = VALUES(config_value)
                """,
                    (new_key, new_value),
                )
            conn.commit()
            log_audit_action("System Setting", f"Added '{new_key}' = '{new_value}'")
            flash(f"Custom setting '{new_key}' successfully added.", "success")
        except Exception as e:
            current_app.logger.error(f"Failed to add setting: {e}")
            flash("Error adding setting to database.", "error")
    else:
        flash("Both Key and Value are required.", "error")

    return redirect(url_for("admin.system_settings"))


@admin_bp.route("/settings/delete", methods=["POST"])
@rbac_required(PERM_MANAGE_SETTINGS)
def delete_setting():
    """Removes a configuration key from the database, reverting it to default."""

    target_key = request.form.get("target_key", "").strip()

    if target_key:
        try:
            conn = get_pariah_db()
            with conn.cursor() as cursor:
                # We do not prevent deleting KNOWN_SETTINGS because deleting them
                # simply causes the get_dynamic_config() function to fall back
                # to the safe defaults defined in schema.py.
                cursor.execute(
                    "DELETE FROM config WHERE config_key = %s", (target_key,)
                )
            conn.commit()
            log_audit_action("System Setting", f"Deleted '{target_key}'")
            flash(
                f"Setting '{target_key}' deleted and reverted to system default.",
                "success",
            )
        except Exception as e:
            current_app.logger.error(f"Failed to delete setting {target_key}: {e}")
            flash("Database error while deleting setting.", "error")
    else:
        flash("No target key specified.", "error")

    return redirect(url_for("admin.system_settings"))


# --- SMART TEXTURE PROXY ---
@admin_bp.route("/texture/<hash_val>")
@rbac_required(PERM_VIEW_ASSETS)
def serve_texture(hash_val):
    """Fetches a texture from FSAssets, decodes JP2 to JPG via OpenCV, caches it, and serves it."""
    if not re.match(r"^[a-fA-F0-9]+$", hash_val):
        abort(400)

    # 1. Check Configurable Cache Path
    cache_dir = get_dynamic_config("texture_cache_path")
    cached_file = os.path.normpath(os.path.join(cache_dir, f"{hash_val}.jpg"))
    can_cache = False

    # Ensure the cache directory is safe and within the fsassets_root
    if not cached_file.startswith(cache_dir):
        abort(403)

    try:
        os.makedirs(cache_dir, exist_ok=True)
        if os.access(cache_dir, os.W_OK):
            can_cache = True
    except Exception:
        pass  # We will fallback to memory-only conversion

    # 2. Serve from Cache if available
    if can_cache and os.path.exists(cached_file):
        return send_from_directory(cache_dir, f"{hash_val}.jpg")

    # 3. Locate Raw Blob
    fsassets_root = get_dynamic_config("fsassets_path")
    if len(hash_val) < 10:
        abort(404)

    rel_path = os.path.join(
        hash_val[0:2], hash_val[2:4], hash_val[4:6], hash_val[6:10], f"{hash_val}.gz"
    )
    full_path = os.path.normpath(os.path.join(fsassets_root, rel_path))

    # Ensure the path is safe and within the fsassets_root
    if not full_path.startswith(fsassets_root):
        abort(403)
    # If the file does not exist, return a 404
    elif not os.path.exists(full_path):
        abort(404)

    # If the file is safe, try to decode it
    try:
        # Unzip -> Decode
        with gzip.open(full_path, "rb") as f:
            uncompressed_bytes = f.read()

        file_bytes = np.asarray(bytearray(uncompressed_bytes), dtype=np.uint8)
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

        if img is None:
            abort(500)

        # 4. Save to Disk OR Serve from RAM
        if can_cache:
            cv2.imwrite(cached_file, img)
            return send_from_directory(cache_dir, f"{hash_val}.jpg")
        else:
            # Fallback: Encode to JPG in memory and send directly
            is_success, buffer = cv2.imencode(".jpg", img)
            if is_success:
                return send_file(io.BytesIO(buffer), mimetype="image/jpeg")
            abort(500)

    except Exception as e:
        current_app.logger.error(f"Failed to decode texture {hash_val}: {e}")
        abort(500)


# --- GALLERY UI ROUTE ---
@admin_bp.route("/gallery")
@rbac_required(PERM_VIEW_ASSETS)
def texture_gallery():
    """Renders a paginated gallery of grid textures.

    Global listings prefer the Pariah ``texture_gallery_snapshot`` table (filled by
    the log worker) so the request path avoids the heavy Robust join. Per-user
    UUID filters use an inverted / selective Robust query. If the snapshot is
    empty, global view falls back to the inverted Robust plan.
    """
    # Check permissions and warn Admin (RESTORED)
    cache_dir = get_dynamic_config("texture_cache_path")
    try:
        if not os.path.exists(cache_dir) or not os.access(cache_dir, os.W_OK):
            flash(
                f"Warning: Texture cache dir ({cache_dir}) is missing or not writable by the 'pariah' user. Images are decoding in RAM (High CPU overhead).",
                "warning",
            )
    except Exception:
        flash(
            f"Warning: Unable to verify cache directory permissions at {cache_dir}.",
            "warning",
        )

    page = int(request.args.get("page", 1))
    per_page = 48
    offset = (page - 1) * per_page
    target_uuid = request.args.get("uuid", "").strip()

    textures = []

    try:
        if target_uuid:
            textures = fetch_textures_inverted(
                get_robust_db(),
                limit=per_page,
                offset=offset,
                owner_uuid=target_uuid,
            )
        else:
            pariah_conn = get_pariah_db()
            if snapshot_count(pariah_conn) > 0:
                textures = fetch_textures_from_snapshot(
                    pariah_conn, limit=per_page, offset=offset
                )
            else:
                textures = fetch_textures_inverted(
                    get_robust_db(), limit=per_page, offset=offset
                )
                flash(
                    "Texture gallery snapshot is empty. Showing a live Robust query; "
                    "it will populate after the next pariah-worker-log run.",
                    "warning",
                )
    except Exception as e:
        current_app.logger.error(f"Gallery Query Failed: {e}")
        flash("Failed to load textures from the database.", "error")

    return render_template(
        "admin/gallery.html", textures=textures, page=page, target_uuid=target_uuid
    )


@admin_bp.route("/audit", methods=["GET"])
@rbac_required(PERM_VIEW_AUDIT)
def audit_log():
    page = int(request.args.get("page", 1))
    per_page = 100
    offset = (page - 1) * per_page
    search = request.args.get("q", "").strip()

    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        if search:
            like_search = f"%{search}%"
            cursor.execute(
                """
                SELECT * FROM audit_log
                WHERE admin_name LIKE %s OR action LIKE %s OR details LIKE %s OR target_uuid = %s
                ORDER BY created_at DESC LIMIT %s OFFSET %s
            """,
                (like_search, like_search, like_search, search, per_page, offset),
            )
        else:
            cursor.execute(
                "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (per_page, offset),
            )

        logs = cursor.fetchall()

    return render_template("admin/audit.html", logs=logs, page=page, search=search)


def _can_view_bot_queue():
    return has_permission(PERM_MANAGE_SETTINGS) or has_permission(PERM_MANAGE_EVENTS)


@admin_bp.route("/bot-queue", methods=["GET", "POST"])
def bot_queue_admin():
    if not session.get("uuid"):
        flash("Please log in.", "error")
        return redirect(url_for("auth.login"))
    if not _can_view_bot_queue():
        flash("Unauthorized: You lack the required portal permissions.", "error")
        return redirect(url_for("comms.news_feed"))

    from app.utils.grid_bot import get_queue_stats, retry_failed_messages

    if request.method == "POST":
        action = request.form.get("action")
        if action == "retry_all":
            retry_failed_messages()
            flash("All failed messages re-queued.", "success")
        elif action == "retry_selected":
            ids = [int(x) for x in request.form.getlist("message_id") if x.isdigit()]
            if ids:
                retry_failed_messages(ids)
                flash(f"Re-queued {len(ids)} message(s).", "success")
        return redirect(url_for("admin.bot_queue_admin"))

    stats, recent = get_queue_stats()
    return render_template("admin/bot_queue.html", stats=stats, recent=recent)
