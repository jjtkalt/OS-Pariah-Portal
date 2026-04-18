ALTER TABLE pending_registrations 
MODIFY COLUMN status ENUM('pending_email', 'pending_email_change', 'pending_approval', 'approved', 'rejected') 
NOT NULL DEFAULT 'pending_email';