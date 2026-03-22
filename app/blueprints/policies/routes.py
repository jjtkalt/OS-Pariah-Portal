import re
from flask import Blueprint, render_template, request, flash, redirect, url_for, session, current_app
from app.utils.db import get_pariah_db, get_dynamic_config
from app.utils.auth_helpers import require_admin

policies_bp = Blueprint('policies', __name__)

@policies_bp.route('/<slug>', methods=['GET'])
def view_policy(slug):
    """Publicly viewable policy with version and timestamp."""
    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT title, body, updated_at, requires_login FROM policies WHERE slug = %s", (slug,))
        policy = cursor.fetchone()

    if not policy:
        flash("Document not found.", "error")
        return redirect(url_for('comms.news_feed'))

    # ENFORCE PRIVACY: Kick guests to login if the document is flagged private
    if policy['requires_login'] and not session.get('uuid'):
        session['next'] = request.url
        flash("You must be logged in to view this document.", "error")
        return redirect(url_for('auth.login'))

    current_version = get_dynamic_config('global_policy_version', '1.0')
    return render_template('policies/view.html', policy=policy, version=current_version)

@policies_bp.route('/admin/manage', methods=['GET'])
@require_admin
def manage_policies():
    """Level 250+ Admin dashboard for policies."""
    if int(session.get('user_level', 0)) < 250:
        flash("Unauthorized. Senior Admin (Level 250+) required.", "error")
        return redirect(url_for('comms.news_feed'))

    pariah_conn = get_pariah_db()
    current_version = get_dynamic_config('global_policy_version', '1.0')
    
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT slug, title, category, requires_login, updated_at FROM policies ORDER BY category ASC, title ASC")
        policies = cursor.fetchall()
        
    return render_template('policies/manage.html', policies=policies, current_version=current_version)

@policies_bp.route('/admin/create', methods=['GET', 'POST'])
@require_admin
def create_policy():
    """Creates a new document."""
    if int(session.get('user_level', 0)) < 250:
        return redirect(url_for('comms.news_feed'))

    if request.method == 'POST':
        raw_slug = request.form.get('slug', '').strip().lower()
        slug = re.sub(r'[^a-z0-9-_]', '-', raw_slug)
        title = request.form.get('title')
        body = request.form.get('body')
        category = request.form.get('category', 'Policy')
        requires_login = request.form.get('requires_login') == 'on'
        
        # STRICT ENFORCEMENT: Only Policies can bump the version
        version_action = request.form.get('version_action') if category == 'Policy' else 'none'

        pariah_conn = get_pariah_db()
        try:
            with pariah_conn.cursor() as cursor:
                cursor.execute("INSERT INTO policies (slug, title, body, category, requires_login) VALUES (%s, %s, %s, %s, %s)", 
                               (slug, title, body, category, requires_login))

                if version_action in ['minor', 'major']:
                    current_version = get_dynamic_config('global_policy_version', '1.0')
                    try:
                        major, minor = map(int, current_version.split('.'))
                        new_version = f"{major + 1}.0" if version_action == 'major' else f"{major}.{minor + 1}"
                    except ValueError:
                        new_version = "2.0"

                    cursor.execute("""
                        INSERT INTO config (config_key, config_value) VALUES ('global_policy_version', %s) 
                        ON DUPLICATE KEY UPDATE config_value = VALUES(config_value)
                    """, (new_version,))
                    flash(f"Policy '{title}' created! Global version bumped to {new_version}.", "success")
                else:
                    flash(f"Document '{title}' created silently.", "success")
                    
            pariah_conn.commit()
            return redirect(url_for('policies.manage_policies'))
        except Exception as e:
            current_app.logger.error(f"Failed to create policy: {e}")
            flash("Failed to create document. That URL slug might already exist.", "error")
            return redirect(url_for('policies.create_policy'))

    return render_template('policies/create.html')

@policies_bp.route('/admin/edit/<slug>', methods=['GET', 'POST'])
@require_admin
def edit_policy(slug):
    """Edits an existing document."""
    if int(session.get('user_level', 0)) < 250:
        return redirect(url_for('comms.news_feed'))

    pariah_conn = get_pariah_db()

    if request.method == 'POST':
        title = request.form.get('title')
        body = request.form.get('body')
        category = request.form.get('category', 'Policy')
        requires_login = request.form.get('requires_login') == 'on'
        
        # STRICT ENFORCEMENT: Only Policies can bump the version
        version_action = request.form.get('version_action') if category == 'Policy' else 'none'

        with pariah_conn.cursor() as cursor:
            cursor.execute("UPDATE policies SET title = %s, body = %s, category = %s, requires_login = %s WHERE slug = %s", 
                           (title, body, category, requires_login, slug))

            if version_action in ['minor', 'major']:
                current_version = get_dynamic_config('global_policy_version', '1.0')
                try:
                    major, minor = map(int, current_version.split('.'))
                    new_version = f"{major + 1}.0" if version_action == 'major' else f"{major}.{minor + 1}"
                except ValueError:
                    new_version = "2.0"

                cursor.execute("""
                    INSERT INTO config (config_key, config_value) VALUES ('global_policy_version', %s) 
                    ON DUPLICATE KEY UPDATE config_value = VALUES(config_value)
                """, (new_version,))
                flash(f"Policy updated. Global version bumped to {new_version}.", "success")
            else:
                flash("Document updated silently.", "success")

        pariah_conn.commit()
        return redirect(url_for('policies.manage_policies'))

    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT slug, title, body, category, requires_login FROM policies WHERE slug = %s", (slug,))
        policy = cursor.fetchone()

    return render_template('policies/edit.html', policy=policy)

@policies_bp.route('/admin/delete/<slug>', methods=['POST'])
@require_admin
def delete_policy(slug):
    if int(session.get('user_level', 0)) < 250:
        return redirect(url_for('comms.news_feed'))

    pariah_conn = get_pariah_db()
    try:
        with pariah_conn.cursor() as cursor:
            cursor.execute("DELETE FROM policies WHERE slug = %s", (slug,))
        pariah_conn.commit()
        flash(f"Document '{slug}' permanently deleted.", "success")
    except Exception as e:
        current_app.logger.error(f"Failed to delete policy {slug}: {e}")
        flash("Error deleting document.", "error")
        
    return redirect(url_for('policies.manage_policies'))
