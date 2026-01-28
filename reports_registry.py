"""
Reports Registry - Tracks all generated property reports
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

REPORTS_DB_PATH = Path(__file__).parent / "reports_registry.db"

def init_reports_db():
    """Initialize the reports registry database."""
    con = sqlite3.connect(str(REPORTS_DB_PATH))
    cur = con.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            report_id TEXT PRIMARY KEY,
            property_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            property_id INTEGER,
            file_size INTEGER,
            status TEXT DEFAULT 'completed',
            user_id INTEGER,
            username TEXT,
            job_number INTEGER
        )
    """)
    
    # Add user_id and username columns if they don't exist (for existing databases)
    try:
        cur.execute("ALTER TABLE reports ADD COLUMN user_id INTEGER")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    try:
        cur.execute("ALTER TABLE reports ADD COLUMN username TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    try:
        cur.execute("ALTER TABLE reports ADD COLUMN job_number INTEGER")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    con.commit()
    con.close()

def register_report(report_id: str, property_name: str, file_path: str, property_id: Optional[int] = None, user_id: Optional[int] = None, username: Optional[str] = None, status: str = 'completed', job_number: Optional[int] = None) -> bool:
    """Register a new report in the registry."""
    try:
        init_reports_db()
        con = sqlite3.connect(str(REPORTS_DB_PATH))
        cur = con.cursor()
        
        # Get file size
        file_size = 0
        if Path(file_path).exists():
            file_size = Path(file_path).stat().st_size
        
        # If job_number not provided, get the next job number for this user
        if job_number is None:
            if user_id is not None:
                cur.execute("""
                    SELECT COALESCE(MAX(job_number), 0) + 1 
                    FROM reports 
                    WHERE user_id = ?
                """, (user_id,))
                result = cur.fetchone()
                job_number = result[0] if result else 1
            else:
                job_number = 1
        
        cur.execute("""
            INSERT OR REPLACE INTO reports 
            (report_id, property_name, file_path, property_id, file_size, status, user_id, username, job_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (report_id, property_name, file_path, property_id, file_size, status, user_id, username, job_number))
        
        con.commit()
        con.close()
        return True
    except Exception as e:
        print(f"[Reports Registry] Error registering report: {e}")
        return False

def update_report_status(report_id: str, status: str, file_path: Optional[str] = None) -> bool:
    """Update the status of a report."""
    try:
        init_reports_db()
        con = sqlite3.connect(str(REPORTS_DB_PATH))
        cur = con.cursor()
        
        if file_path:
            # Update file path and size if provided
            file_size = 0
            if Path(file_path).exists():
                file_size = Path(file_path).stat().st_size
            cur.execute("""
                UPDATE reports 
                SET status = ?, file_path = ?, file_size = ?
                WHERE report_id = ?
            """, (status, file_path, file_size, report_id))
        else:
            cur.execute("""
                UPDATE reports 
                SET status = ?
                WHERE report_id = ?
            """, (status, report_id))
        
        con.commit()
        con.close()
        return True
    except Exception as e:
        print(f"[Reports Registry] Error updating report status: {e}")
        return False

def get_all_reports(limit: int = 100, user_id: Optional[int] = None) -> List[Dict]:
    """Get all reports, most recent first. If user_id is provided, filter by user."""
    try:
        init_reports_db()
        con = sqlite3.connect(str(REPORTS_DB_PATH))
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        
        if user_id is not None:
            cur.execute("""
                SELECT report_id, property_name, file_path, created_at, property_id, file_size, status, user_id, username, job_number
                FROM reports
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (user_id, limit))
        else:
            cur.execute("""
                SELECT report_id, property_name, file_path, created_at, property_id, file_size, status, user_id, username, job_number
                FROM reports
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
        
        rows = cur.fetchall()
        con.close()
        
        reports = []
        for row in rows:
            # Handle user_id and username - they might not exist in older databases
            user_id = None
            username = 'Unknown'
            try:
                user_id = row['user_id']
            except (KeyError, IndexError):
                pass
            
            try:
                username = row['username'] or 'Unknown'
            except (KeyError, IndexError):
                pass
            
            # Handle job_number - might not exist in older databases
            job_number = None
            try:
                job_number = row['job_number']
            except (KeyError, IndexError):
                pass
            
            reports.append({
                'report_id': row['report_id'],
                'property_name': row['property_name'],
                'file_path': row['file_path'],
                'created_at': row['created_at'],
                'property_id': row['property_id'],
                'file_size': row['file_size'],
                'status': row['status'],
                'user_id': user_id,
                'username': username,
                'job_number': job_number,
                'exists': Path(row['file_path']).exists()
            })
        
        return reports
    except Exception as e:
        print(f"[Reports Registry] Error getting reports: {e}")
        return []

def get_report(report_id: str) -> Optional[Dict]:
    """Get a specific report by ID."""
    try:
        init_reports_db()
        con = sqlite3.connect(str(REPORTS_DB_PATH))
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        
        cur.execute("""
            SELECT report_id, property_name, file_path, created_at, property_id, file_size, status, user_id, username, job_number
            FROM reports
            WHERE report_id = ?
        """, (report_id,))
        
        row = cur.fetchone()
        con.close()
        
        if row:
            # Handle user_id and username - they might not exist in older databases
            user_id = None
            username = 'Unknown'
            try:
                user_id = row['user_id']
            except (KeyError, IndexError):
                pass
            
            try:
                username = row['username'] or 'Unknown'
            except (KeyError, IndexError):
                pass
            
            # Handle job_number - might not exist in older databases
            job_number = None
            try:
                job_number = row['job_number']
            except (KeyError, IndexError):
                pass
            
            return {
                'report_id': row['report_id'],
                'property_name': row['property_name'],
                'file_path': row['file_path'],
                'created_at': row['created_at'],
                'property_id': row['property_id'],
                'file_size': row['file_size'],
                'status': row['status'],
                'user_id': user_id,
                'username': username,
                'job_number': job_number,
                'exists': Path(row['file_path']).exists()
            }
        return None
    except Exception as e:
        print(f"[Reports Registry] Error getting report: {e}")
        return None

def delete_report(report_id: str) -> bool:
    """Delete a report from the registry."""
    try:
        init_reports_db()
        con = sqlite3.connect(str(REPORTS_DB_PATH))
        cur = con.cursor()
        
        cur.execute("DELETE FROM reports WHERE report_id = ?", (report_id,))
        
        con.commit()
        con.close()
        return True
    except Exception as e:
        print(f"[Reports Registry] Error deleting report: {e}")
        return False

def clear_all_reports() -> bool:
    """Clear all reports from the registry (used on server startup)."""
    try:
        init_reports_db()
        con = sqlite3.connect(str(REPORTS_DB_PATH))
        cur = con.cursor()
        
        cur.execute("DELETE FROM reports")
        
        con.commit()
        con.close()
        print("[Reports Registry] All reports cleared from database")
        return True
    except Exception as e:
        print(f"[Reports Registry] Error clearing reports: {e}")
        return False

# Initialize on import
init_reports_db()

