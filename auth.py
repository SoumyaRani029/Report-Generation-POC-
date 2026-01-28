"""
User Authentication Module - Handles user registration, login, and session management
"""
import sqlite3
import hashlib
import secrets
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple

AUTH_DB_PATH = Path(__file__).parent / "users.db"

def init_auth_db():
    """Initialize the authentication database."""
    con = sqlite3.connect(str(AUTH_DB_PATH))
    cur = con.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    """)
    
    con.commit()
    con.close()

def hash_password(password: str) -> str:
    """Hash a password using SHA-256 with salt."""
    salt = secrets.token_hex(16)
    password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}:{password_hash}"

def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a hash."""
    try:
        salt, stored_hash = password_hash.split(':')
        computed_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return computed_hash == stored_hash
    except:
        return False

def register_user(username: str, email: str, password: str) -> Tuple[bool, str, Optional[Dict]]:
    """
    Register a new user.
    Returns: (success, message, user_data)
    """
    try:
        init_auth_db()
        con = sqlite3.connect(str(AUTH_DB_PATH))
        cur = con.cursor()
        
        # Validate inputs
        if not username or len(username) < 3:
            return False, "Username must be at least 3 characters long", None
        
        if not email or '@' not in email:
            return False, "Invalid email address", None
        
        if not password or len(password) < 6:
            return False, "Password must be at least 6 characters long", None
        
        # Check if username exists
        cur.execute("SELECT user_id FROM users WHERE username = ?", (username,))
        if cur.fetchone():
            con.close()
            return False, "Username already exists", None
        
        # Check if email exists
        cur.execute("SELECT user_id FROM users WHERE email = ?", (email,))
        if cur.fetchone():
            con.close()
            return False, "Email already registered", None
        
        # Create user
        password_hash = hash_password(password)
        cur.execute("""
            INSERT INTO users (username, email, password_hash)
            VALUES (?, ?, ?)
        """, (username, email, password_hash))
        
        con.commit()
        user_id = cur.lastrowid
        con.close()
        
        return True, "User registered successfully", {
            'user_id': user_id,
            'username': username,
            'email': email
        }
    except sqlite3.IntegrityError:
        return False, "Username or email already exists", None
    except Exception as e:
        return False, f"Registration error: {str(e)}", None

def authenticate_user(username: str, password: str) -> Tuple[bool, str, Optional[Dict]]:
    """
    Authenticate a user.
    Returns: (success, message, user_data)
    """
    try:
        init_auth_db()
        con = sqlite3.connect(str(AUTH_DB_PATH))
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        
        # Find user by username or email
        cur.execute("""
            SELECT user_id, username, email, password_hash, is_active
            FROM users
            WHERE (username = ? OR email = ?) AND is_active = 1
        """, (username, username))
        
        user = cur.fetchone()
        if not user:
            con.close()
            return False, "Invalid username/email or password", None
        
        # Verify password
        if not verify_password(password, user['password_hash']):
            con.close()
            return False, "Invalid username/email or password", None
        
        # Update last login
        cur.execute("""
            UPDATE users SET last_login = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (user['user_id'],))
        con.commit()
        con.close()
        
        return True, "Login successful", {
            'user_id': user['user_id'],
            'username': user['username'],
            'email': user['email']
        }
    except Exception as e:
        return False, f"Authentication error: {str(e)}", None

def get_user_by_id(user_id: int) -> Optional[Dict]:
    """Get user information by user_id."""
    try:
        init_auth_db()
        con = sqlite3.connect(str(AUTH_DB_PATH))
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        
        cur.execute("""
            SELECT user_id, username, email, created_at, last_login
            FROM users
            WHERE user_id = ? AND is_active = 1
        """, (user_id,))
        
        user = cur.fetchone()
        con.close()
        
        if user:
            return {
                'user_id': user['user_id'],
                'username': user['username'],
                'email': user['email'],
                'created_at': user['created_at'],
                'last_login': user['last_login']
            }
        return None
    except Exception as e:
        print(f"[Auth] Error getting user: {e}")
        return None

# Initialize on import
init_auth_db()

