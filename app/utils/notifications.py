import smtplib
from email.message import EmailMessage
from flask import current_app, url_for
from app.utils.db import get_dynamic_config
import requests
import urllib.request
import urllib.parse
import json
import uuid

def send_matrix_discord_webhook(title, message, color=3447003, fields=None):
    """Fires off notifications to Discord and/or Matrix based on dynamic config."""
    discord_url = get_dynamic_config('discord_webhook_url')
    matrix_url = get_dynamic_config('matrix_webhook_url')
    matrix_token = get_dynamic_config('matrix_access_token')
    matrix_room = get_dynamic_config('matrix_room_id')

    if discord_url:
        discord_data = {
            "embeds": [{
                "title": title,
                "description": message,
                "color": color,
                "fields": fields or []
            }]
        }
        try:
            requests.post(discord_url, json=discord_data, timeout=5)
        except Exception as e:
            current_app.logger.error(f"Discord webhook failed: {e}")

    if matrix_url and matrix_token and matrix_room:
        txn_id = str(uuid.uuid4())
        base_url = matrix_url.rstrip('/')
        url = f"{base_url}/_matrix/client/v3/rooms/{urllib.parse.quote(matrix_room)}/send/m.room.message/{txn_id}"
        matrix_body = f"[{title}]\n{message}"
        payload = json.dumps({"msgtype": "m.text", "body": matrix_body}).encode('utf-8')

        req = urllib.request.Request(url, data=payload, method='PUT')
        req.add_header('Authorization', f'Bearer {matrix_token}')
        req.add_header('Content-Type', 'application/json')

        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                pass
        except Exception as e:
            current_app.logger.error(f"Matrix webhook failed: {e}")

def send_verification_email(to_email, token):
    """Generates the unique link and emails the user."""
    grid_name = get_dynamic_config('grid_name')
    smtp_server = get_dynamic_config('smtp_server')
    smtp_port = int(get_dynamic_config('smtp_port'))
    smtp_user = get_dynamic_config('smtp_user')
    smtp_pass = get_dynamic_config('smtp_pass')
    smtp_from = get_dynamic_config('smtp_from')
    
    # Generate the absolute URL to the verification endpoint
    verify_url = url_for('register.verify_email', token=token, _external=True)
    
    msg = EmailMessage()
    msg.set_content(
        f"Welcome to {grid_name}!\n\n"
        f"Please verify your email address to complete your registration by clicking the link below:\n\n"
        f"{verify_url}\n\n"
        f"If you did not request this, please ignore this email.\n\n"
        f"- The {grid_name} Team"
    )
    msg['Subject'] = f"Verify your {grid_name} Registration"
    msg['From'] = smtp_from
    msg['To'] = to_email
    
    # Safe fallback if SMTP isn't configured yet
    if not smtp_server:
        current_app.logger.warning(f"SMTP not configured! Verification link for {to_email} is: {verify_url}")
        return
        
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    except Exception as e:
        current_app.logger.error(f"Failed to send verification email to {to_email}: {e}")
        current_app.logger.info(f"FALLBACK VERIFICATION LINK for {to_email}: {verify_url}")

def send_approval_email(to_email, grid_name):
    """Sends the welcome email to the user once staff approves them."""
    smtp_server = get_dynamic_config('smtp_server')
    smtp_port = int(get_dynamic_config('smtp_port'))
    smtp_user = get_dynamic_config('smtp_user')
    smtp_pass = get_dynamic_config('smtp_pass')
    smtp_from = get_dynamic_config('smtp_from')

    msg = EmailMessage()
    msg.set_content(
        f"Hello,\n\n"
        f"Your application to {grid_name} has been approved by our staff! You may now log into the grid using the viewer of your choice.\n\n"
        f"Welcome to the community!\n"
        f"- The {grid_name} Staff"
    )
    msg['Subject'] = f"Your {grid_name} Account is Approved!"
    msg['From'] = smtp_from
    msg['To'] = to_email

    if not smtp_server:
        return

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    except Exception as e:
        current_app.logger.error(f"Failed to send approval email to {to_email}: {e}")

def notify_staff_new_app(first_name, last_name, user_uuid, inviter, discord, matrix, other_info):
    """Sends a formatted payload to the configured Matrix/Discord webhook."""
    message = f"**{first_name} {last_name}** has verified their email and is awaiting approval.\n"
    message += f"**UUID:** {user_uuid}\n"

    if inviter:
        message += f"**Invited By:** {inviter}\n"
    if discord:
        message += f"**Discord:** {discord}\n"
    if matrix:
        message += f"**Matrix:** {matrix}\n"
    if other_info:
        message += f"**Reason/Info:** {other_info}\n"

    send_matrix_discord_webhook(
        title="🆕 New Grid Application",
        message=message,
        color=3447003 # Blue
    )

def send_ticket_transcript_email(to_email, ticket_id, subject, reply_body, replier_name):
    """Sends a ticket reply transcript to the user/guest."""
    grid_name = get_dynamic_config('grid_name')
    smtp_server = get_dynamic_config('smtp_server')
    smtp_port = int(get_dynamic_config('smtp_port'))
    smtp_user = get_dynamic_config('smtp_user')
    smtp_pass = get_dynamic_config('smtp_pass')
    smtp_from = get_dynamic_config('smtp_from')

    if not smtp_server or not to_email:
        return

    msg = EmailMessage()
    msg.set_content(
        f"Hello,\n\n"
        f"Your support ticket #{ticket_id} ({subject}) has been updated by {replier_name}.\n\n"
        f"--- Message ---\n"
        f"{reply_body}\n"
        f"---------------\n\n"
        f"You can view the full ticket or reply by logging into the {grid_name} portal.\n"
        f"(Note: If you submitted this ticket as a Guest, you will not be able to log in to view it. Please reply directly to staff if they provided an alternate contact method.)\n\n"
        f"- The {grid_name} Staff"
    )
    msg['Subject'] = f"Update on Ticket #{ticket_id}: {subject}"
    msg['From'] = smtp_from
    msg['To'] = to_email

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    except Exception as e:
        current_app.logger.error(f"Failed to send ticket transcript to {to_email}: {e}")

def send_password_reset_email(to_email, token):
    """Sends the secure password reset link to the user."""
    grid_name = get_dynamic_config('grid_name')
    smtp_server = get_dynamic_config('smtp_server')
    smtp_port = int(get_dynamic_config('smtp_port'))
    smtp_user = get_dynamic_config('smtp_user')
    smtp_pass = get_dynamic_config('smtp_pass')
    smtp_from = get_dynamic_config('smtp_from')

    reset_url = url_for('auth.reset_password', token=token, _external=True)

    msg = EmailMessage()
    msg.set_content(
        f"Hello,\n\n"
        f"We received a request to reset your OpenSimulator password for {grid_name}.\n\n"
        f"Click the link below to securely choose a new password:\n"
        f"{reset_url}\n\n"
        f"If you did not request this, you can safely ignore this email. This link will expire in 1 hour.\n\n"
        f"- The {grid_name} Team"
    )
    msg['Subject'] = f"Password Reset Request - {grid_name}"
    msg['From'] = smtp_from
    msg['To'] = to_email

    if not smtp_server:
        current_app.logger.warning(f"SMTP NOT CONFIGURED. Password Reset Link for {to_email}: {reset_url}")
        return

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    except Exception as e:
        current_app.logger.error(f"Failed to send password reset to {to_email}: {e}")
