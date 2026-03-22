from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from app.utils.db import get_pariah_db
from app.utils.auth_helpers import require_admin

comms_bp = Blueprint('comms', __name__, url_prefix='/comms')

@comms_bp.route('/news', methods=['GET'])
def news_feed():
    """Publicly accessible news feed and global alerts."""
    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        cursor.execute("""
            SELECT id, title, body, author_name, created_at, is_alert 
            FROM global_news 
            ORDER BY created_at DESC LIMIT 20
        """)
        news_items = cursor.fetchall()
        
    return render_template('comms/news_feed.html', news_items=news_items)

@comms_bp.route('/admin/post', methods=['GET', 'POST'])
@require_admin
def post_news():
    """Admin interface to post news or global alerts."""
    if request.method == 'POST':
        title = request.form.get('title')
        body = request.form.get('body')
        is_alert = request.form.get('is_alert') == 'on' # High priority sticky alert
        
        pariah_conn = get_pariah_db()
        with pariah_conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO global_news (title, body, author_uuid, author_name, is_alert) 
                VALUES (%s, %s, %s, %s, %s)
            """, (title, body, session['uuid'], session['name'], is_alert))
        pariah_conn.commit()
        
        flash('News item posted successfully.', 'success')
        return redirect(url_for('comms.news_feed'))
        
    return render_template('comms/post_news.html')

@comms_bp.route('/notices', methods=['GET'])
def user_notices():
    """User-specific inbox for ticket updates, backup completions, etc."""
    if not session.get('uuid'):
        return redirect(url_for('auth.login'))
        
    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        # Fetch unread notices
        cursor.execute("""
            SELECT id, message, created_at, is_read 
            FROM user_notices 
            WHERE user_uuid = %s 
            ORDER BY created_at DESC LIMIT 50
        """, (session['uuid'],))
        notices = cursor.fetchall()
        
        # Mark as read
        cursor.execute("UPDATE user_notices SET is_read = TRUE WHERE user_uuid = %s AND is_read = FALSE", (session['uuid'],))
    pariah_conn.commit()
    
    return render_template('comms/user_notices.html', notices=notices)

@comms_bp.route('/news/delete/<int:news_id>', methods=['POST'])
@require_admin
def delete_news(news_id):
    """Permanently deletes a news/announcement item."""
    if int(session.get('user_level', 0)) < 250:
        flash("Unauthorized. Senior Admin clearance required.", "error")
        return redirect(url_for('comms.news_feed'))

    try:
        pariah_conn = get_pariah_db()
        with pariah_conn.cursor() as cursor:
            cursor.execute("DELETE FROM global_news WHERE id = %s", (news_id,))
        pariah_conn.commit()
        flash("Announcement permanently deleted.", "success")
    except Exception as e:
        current_app.logger.error(f"Failed to delete news item {news_id}: {e}")
        flash("A database error occurred while deleting the announcement.", "error")

    return redirect(url_for('comms.news_feed'))
