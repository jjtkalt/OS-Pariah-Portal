from flask import g, current_app
import app as main_app

def get_robust_db():
    if 'robust_conn' not in g:
        try:
            g.robust_conn = main_app.robust_pool.connection()
        except Exception as e:
            current_app.logger.error(f"Failed to get Robust DB connection: {e}")
            raise
    return g.robust_conn

def get_pariah_db():
    if 'pariah_conn' not in g:
        try:
            g.pariah_conn = main_app.pariah_pool.connection()
        except Exception as e:
            current_app.logger.error(f"Failed to get Pariah DB connection: {e}")
            raise
    return g.pariah_conn

def get_dynamic_config(key, default=None):
    conn = get_pariah_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT config_value FROM config WHERE config_key = %s", (key,))
            result = cursor.fetchone()
            if result:
                return result['config_value']
            return default
    except Exception as e:
        current_app.logger.error(f"Error fetching config '{key}': {e}")
        return default
