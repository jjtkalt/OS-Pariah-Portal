import os
import uuid
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, send_from_directory
from app.utils.db import get_pariah_db, get_robust_db, get_dynamic_config
from app.blueprints.auth.routes import verify_turnstile
from app.utils.notifications import send_matrix_discord_webhook, send_ticket_transcript_email

tickets_bp = Blueprint('tickets', __name__, url_prefix='/tickets')

def allowed_file(filename):
    allowed_str = get_dynamic_config('allowed_attachment_exts', 'png,jpg,jpeg,gif,txt,pdf,log')
    allowed_exts = [ext.strip().lower() for ext in allowed_str.split(',')]
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_exts

@tickets_bp.route('/')
def index():
    user_uuid = session.get('uuid')
    is_admin = session.get('is_admin', False)
    status_filter = request.args.get('status', 'All Open')
    tickets = []

    if user_uuid:
        pariah_conn = get_pariah_db()
        with pariah_conn.cursor() as cursor:
            if is_admin:
                if status_filter == 'All Open':
                    open_statuses = ('Open', 'In Progress', 'On Hold', 'Waiting on User', 'Waiting on Staff')
                    cursor.execute("SELECT * FROM tickets WHERE status IN %s ORDER BY updated_at DESC", (open_statuses,))
                elif status_filter == 'All Tickets':
                    cursor.execute("SELECT * FROM tickets ORDER BY updated_at DESC")
                elif status_filter:
                    cursor.execute("SELECT * FROM tickets WHERE status = %s ORDER BY updated_at DESC", (status_filter,))
            else:
                cursor.execute("SELECT * FROM tickets WHERE user_uuid = %s ORDER BY updated_at DESC", (user_uuid,))
            tickets = cursor.fetchall()

    return render_template('tickets/index.html', tickets=tickets, current_filter=status_filter)

@tickets_bp.route('/new', methods=['GET', 'POST'])
def new_ticket():
    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        category = request.form.get('category', 'General Support')
        message = request.form.get('message', '').strip()
        attachment = request.files.get('attachment')
        email = request.form.get('email', '').strip()

        if not subject or not message:
            flash('Subject and Message are required fields.', 'error')
            return redirect(url_for('tickets.new_ticket'))

        user_uuid = session.get('uuid')
        user_name = session.get('name', 'Guest')
        guest_ip = None

        # --- GUEST HANDLING ---
        if not user_uuid:
            turnstile_response = request.form.get('cf-turnstile-response')
            if not verify_turnstile(turnstile_response):
                flash('Security check failed. Please try again.', 'error')
                return redirect(url_for('tickets.new_ticket'))
            if not email:
                flash('An email address is required for guest tickets so we can reply to you.', 'error')
                return redirect(url_for('tickets.new_ticket'))

            guest_ip = request.headers.get('X-Real-IP', request.remote_addr)
            message = f"[GUEST SUBMISSION - IP: {guest_ip}]\n\n{message}"

        conn = get_pariah_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO tickets (user_uuid, user_name, user_email, subject, category, body, status, guest_ip)
                    VALUES (%s, %s, %s, %s, %s, %s, 'Open', %s)
                """, (user_uuid, user_name, email, subject, category, message, guest_ip))

                ticket_id = cursor.lastrowid

                if attachment and attachment.filename and allowed_file(attachment.filename):
                    filename = secure_filename(attachment.filename)
                    unique_filename = f"{uuid.uuid4().hex}_{filename}"
                    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'tickets')
                    os.makedirs(upload_folder, exist_ok=True)
                    file_path = os.path.join(upload_folder, unique_filename)
                    attachment.save(file_path)

                    cursor.execute("""
                        INSERT INTO ticket_attachments (ticket_id, uploader_uuid, filename, file_path)
                        VALUES (%s, %s, %s, %s)
                    """, (ticket_id, user_uuid or 'guest', filename, unique_filename))

            conn.commit()

            send_matrix_discord_webhook(
                title=f"🎫 New Ticket: {subject}",
                message=f"**Category:** {category}\n**User:** {user_name}\n\n{message[:200]}...",
                color=16753920
            )

            flash('Your ticket has been submitted successfully!', 'success')
            if not user_uuid:
                return redirect(url_for('auth.login'))
            return redirect(url_for('tickets.index'))

        except Exception as e:
            current_app.logger.error(f"Failed to create ticket: {e}")
            flash('A database error occurred while saving your ticket.', 'error')

    # Explicitly grab the site key from the dynamic config!
    site_key = get_dynamic_config('TURNSTILE_SITE_KEY', '3x00000000000000000000FF')
    return render_template('tickets/new_ticket.html', site_key=site_key)

@tickets_bp.route('/view/<int:ticket_id>')
def view(ticket_id):
    user_uuid = session.get('uuid')
    is_admin = session.get('is_admin', False)

    if not user_uuid:
        flash('You must be logged in to view tickets.', 'error')
        return redirect(url_for('auth.login'))

    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT * FROM tickets WHERE id = %s", (ticket_id,))
        ticket = cursor.fetchone()
        
        if not ticket:
            flash('Ticket not found.', 'error')
            return redirect(url_for('tickets.index'))
            
        if not is_admin and ticket['user_uuid'] != user_uuid:
            flash('Access denied. You do not own this ticket.', 'error')
            return redirect(url_for('tickets.index'))

        cursor.execute("SELECT * FROM ticket_replies WHERE ticket_id = %s ORDER BY created_at ASC", (ticket_id,))
        replies = cursor.fetchall()

        cursor.execute("SELECT * FROM ticket_attachments WHERE ticket_id = %s", (ticket_id,))
        attachments = cursor.fetchall()

    allow_delete = False
    if is_admin:
        allow_delete = get_dynamic_config('allow_ticket_deletion', 'false') == 'true'

    return render_template('tickets/view.html', ticket=ticket, replies=replies, attachments=attachments, allow_delete=allow_delete)

@tickets_bp.route('/<int:ticket_id>/attachment/<filename>')
def view_attachment(ticket_id, filename):
    user_uuid = session.get('uuid')
    if not user_uuid:
        return redirect(url_for('auth.login'))

    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT user_uuid FROM tickets WHERE id = %s", (ticket_id,))
        ticket = cursor.fetchone()

    if not ticket or (ticket['user_uuid'] != user_uuid and not session.get('is_admin')):
        flash('Access denied.', 'error')
        return redirect(url_for('tickets.index'))

    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'tickets')
    return send_from_directory(upload_folder, filename)

@tickets_bp.route('/<int:ticket_id>/reply', methods=['POST'])
def reply_ticket(ticket_id):
    if 'uuid' not in session:
        return redirect(url_for('auth.login'))

    reply_body = request.form.get('message', '').strip() or request.form.get('body', '').strip()
    attachment = request.files.get('attachment')
    explicit_status = request.form.get('status')

    if not reply_body and not (attachment and attachment.filename) and not explicit_status:
        flash('You must provide a message or change the status.', 'error')
        return redirect(url_for('tickets.view', ticket_id=ticket_id))

    user_uuid = session.get('uuid')
    user_name = session.get('name', 'Staff')
    is_admin = session.get('is_admin', False)

    conn = get_pariah_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM tickets WHERE id = %s", (ticket_id,))
            ticket = cursor.fetchone()
            if not ticket:
                return redirect(url_for('tickets.index'))

            # --- SMART ASSIGNMENT & STATUS LOGIC ---
            assigned_uuid = ticket['assigned_to_uuid']
            assigned_name = ticket['assigned_to_name']
            new_status = explicit_status

            if is_admin:
                # Admins auto-claim tickets they touch (unless closing them out entirely)
                if new_status not in ['Completed', 'Withdrawn', 'Will not work', 'No Response']:
                    assigned_uuid = user_uuid
                    assigned_name = user_name
                # Default status if none provided
                if not new_status:
                    new_status = "Completed" if not ticket['user_uuid'] else "Waiting on User"
            else:
                # Users replying pushes it back to staff
                if not new_status:
                    new_status = "Waiting on Staff"

            # 1. Insert the reply
            reply_id = None
            if reply_body or (attachment and attachment.filename):
                # Storing the replier's name in 'replier_email' since we don't have a name column in that table yet!
                cursor.execute("""
                    INSERT INTO ticket_replies (ticket_id, replier_uuid, replier_email, body)
                    VALUES (%s, %s, %s, %s)
                """, (ticket_id, user_uuid, user_name, reply_body))
                reply_id = cursor.lastrowid

                # Process Attachment
                if attachment and attachment.filename and allowed_file(attachment.filename):
                    filename = secure_filename(attachment.filename)
                    unique_filename = f"{uuid.uuid4().hex}_{filename}"
                    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'tickets')
                    os.makedirs(upload_folder, exist_ok=True)
                    file_path = os.path.join(upload_folder, unique_filename)
                    attachment.save(file_path)

                    cursor.execute("""
                        INSERT INTO ticket_attachments (ticket_id, reply_id, uploader_uuid, filename, file_path)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (ticket_id, reply_id, user_uuid, filename, unique_filename))

            # 2. Touch the main ticket
            cursor.execute("""
                UPDATE tickets
                SET status = %s, assigned_to_uuid = %s, assigned_to_name = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (new_status, assigned_uuid, assigned_name, ticket_id))

        conn.commit()

        # 3. Fire off the email transcript if Admin replies
        if is_admin and ticket['user_email'] and reply_body:
            send_ticket_transcript_email(ticket['user_email'], ticket_id, ticket['subject'], reply_body, user_name)

        flash('Ticket updated successfully.', 'success')

    except Exception as e:
        current_app.logger.error(f"Failed to update ticket {ticket_id}: {e}")
        flash('A database error occurred while updating the ticket.', 'error')

    return redirect(url_for('tickets.view', ticket_id=ticket_id))

@tickets_bp.route('/<int:ticket_id>/delete', methods=['POST'])
def delete_ticket(ticket_id):
    if int(session.get('user_level', 0)) < 250 or get_dynamic_config('allow_ticket_deletion', 'false') != 'true':
        flash("Unauthorized: Ticket deletion is disabled globally or you lack clearance.", "error")
        return redirect(url_for('tickets.view', ticket_id=ticket_id))

    conn = get_pariah_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM tickets WHERE id = %s", (ticket_id,))
        conn.commit()
        flash("Ticket and all associated replies deleted permanently.", "success")
    except Exception as e:
        current_app.logger.error(f"Delete failed: {e}")
        flash("A database error occurred during deletion.", "error")

    return redirect(url_for('tickets.index'))
