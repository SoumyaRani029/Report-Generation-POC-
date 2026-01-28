# file: web_app.py
"""Flask web application for Property Valuation Report Generator."""
from flask import Flask, render_template, request, jsonify, send_file, session, Response, stream_with_context
from werkzeug.utils import secure_filename
import os
import json
import shutil
import tempfile
from pathlib import Path
from main import generate_report_from_files
import uuid
import webbrowser
import threading
import time
from threading import Thread
from queue import Queue
from performance_tracker import log_capture, get_timings, get_recent_logs, clear_timings
from dashboard_api import dashboard_api
from reports_registry import register_report, get_all_reports, get_report, delete_report, update_report_status, clear_all_reports
from auth import register_user, authenticate_user, get_user_by_id
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
app.config['UPLOAD_FOLDER'] = Path(tempfile.gettempdir()) / 'property_uploads'
app.config['DEBUG'] = True  # Enable debug mode to s                                                                                                                ee detailed error messages
app.config['TEMPLATES_AUTO_RELOAD'] = True  # Automatically reload templates when they change

# Enable CORS for React app
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Register dashboard API blueprint
app.register_blueprint(dashboard_api)

# Sequential processing queue for reports (FIFO - First In First Out)
# This ensures reports are processed one at a time in the order they were uploaded
report_queue = Queue()
queue_lock = threading.Lock()
is_worker_running = False

# Allowed file extensions
ALLOWED_DOCUMENTS = {'pdf', 'txt'}
ALLOWED_IMAGES = {'jpg', 'jpeg', 'png', 'bmp', 'tiff', 'webp'}

def allowed_file(filename, allowed_set):
    """Check if file extension is allowed."""
    if not filename or '.' not in filename:
        return False
    parts = filename.rsplit('.', 1)
    if len(parts) < 2:
        return False
    return parts[1].lower() in allowed_set

def process_report_queue():
    """Worker thread that processes reports sequentially from the queue (FIFO)."""
    global is_worker_running
    
    while True:
        try:
            # Get next report from queue (blocks until one is available)
            report_task = report_queue.get(timeout=1)
            
            report_id = report_task['report_id']
            documents = report_task['documents']
            images = report_task['images']
            property_name = report_task['property_name']
            upload_dir = report_task['upload_dir']
            job_number = report_task['job_number']
            status_callback = report_task['status_callback']
            
            print(f"[INFO] [QUEUE] Processing report {report_id} (Job {job_number}). Queue remaining: {report_queue.qsize()}")
            
            try:
                print(f"[INFO] Starting report generation for {len(documents)} documents and {len(images)} images (Report ID: {report_id}, Job: {job_number})")
                try:
                    output_pdf, error = generate_report_from_files(
                        documents, images, property_name, status_callback
                    )
                except (IndexError, ValueError) as list_err:
                    import traceback
                    error_trace = traceback.format_exc()
                    error_msg = f"List/Index Error in report generation: {str(list_err)}"
                    print(f"[ERROR] {error_msg}")
                    print(f"[ERROR] Full traceback:\n{error_trace}")
                    # Update report status to error
                    update_report_status(report_id, 'error')
                    # Cleanup upload folder
                    try:
                        shutil.rmtree(upload_dir)
                    except:
                        pass
                    report_queue.task_done()
                    continue
                
                if error:
                    print(f"[ERROR] Report generation failed: {error}")
                    # Update report status to error
                    update_report_status(report_id, 'error')
                    # Cleanup upload folder
                    try:
                        shutil.rmtree(upload_dir)
                    except:
                        pass
                    report_queue.task_done()
                    continue
                
                if not output_pdf or not Path(output_pdf).exists():
                    error_msg = f"Report file not found at {output_pdf}"
                    print(f"[ERROR] {error_msg}")
                    update_report_status(report_id, 'error')
                    report_queue.task_done()
                    continue
                
                print(f"[INFO] Report generated successfully: {output_pdf} (Report ID: {report_id}, Job: {job_number})")
                
                # Update report in registry with final file path and completed status
                update_report_status(report_id, 'completed', output_pdf)
                
                # Log completion message to dashboard
                try:
                    completion_msg = f"✅ Job {job_number} is completed"
                    log_capture.log(completion_msg, "SUCCESS")
                    print(f"[INFO] {completion_msg}")
                except:
                    pass  # If logging not available, continue anyway
                
                # Mark task as done
                report_queue.task_done()
                print(f"[INFO] [QUEUE] Completed report {report_id} (Job {job_number}). Queue remaining: {report_queue.qsize()}")
                    
            except Exception as gen_error:
                import traceback
                error_trace = traceback.format_exc()
                error_msg = f"Error during report generation: {str(gen_error)}"
                print(f"[ERROR] {error_msg}")
                print(f"[ERROR] Traceback: {error_trace}")
                # Update report status to error
                update_report_status(report_id, 'error')
                # Cleanup upload folder
                try:
                    shutil.rmtree(upload_dir)
                except:
                    pass
                report_queue.task_done()
                
        except Exception as queue_error:
            # Timeout or other queue error - continue waiting
            if "Empty" not in str(queue_error) and "timeout" not in str(queue_error).lower():
                print(f"[ERROR] Queue processing error: {queue_error}")
            continue

def login_required(f):
    """Decorator to require login for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            # Check if this is an API request (JSON expected)
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({
                    'success': False,
                    'error': 'Authentication required',
                    'redirect': '/login'
                }), 401
            else:
                # For regular page requests, redirect to login
                from flask import redirect, url_for
                return redirect('/login?redirect=' + request.path)
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    """Main page - React.js Upload Interface."""
    return render_template('app.html')

@app.route('/login')
def login_page():
    """Login page."""
    return render_template('login.html')

@app.route('/signup')
def signup_page():
    """Signup page."""
    return render_template('signup.html')

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """API endpoint for user login."""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({
                'success': False,
                'error': 'Username and password are required'
            }), 400
        
        success, message, user_data = authenticate_user(username, password)
        
        if success:
            session['user_id'] = user_data['user_id']
            session['username'] = user_data['username']
            session['email'] = user_data['email']
            return jsonify({
                'success': True,
                'message': message,
                'user': user_data
            })
        else:
            return jsonify({
                'success': False,
                'error': message
            }), 401
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Login error: {str(e)}'
        }), 500

@app.route('/api/auth/signup', methods=['POST'])
def api_signup():
    """API endpoint for user registration."""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        if not username or not email or not password:
            return jsonify({
                'success': False,
                'error': 'Username, email, and password are required'
            }), 400
        
        success, message, user_data = register_user(username, email, password)
        
        if success:
            # Auto-login after signup
            session['user_id'] = user_data['user_id']
            session['username'] = user_data['username']
            session['email'] = user_data['email']
            return jsonify({
                'success': True,
                'message': message,
                'user': user_data
            })
        else:
            return jsonify({
                'success': False,
                'error': message
            }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Registration error: {str(e)}'
        }), 500

@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    """API endpoint for user logout."""
    session.clear()
    return jsonify({
        'success': True,
        'message': 'Logged out successfully'
    })

@app.route('/api/auth/current', methods=['GET'])
def api_current_user():
    """Get current logged-in user."""
    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'authenticated': False
        }), 401
    
    user = get_user_by_id(session['user_id'])
    if user:
        return jsonify({
            'success': True,
            'authenticated': True,
            'user': user
        })
    else:
        session.clear()
        return jsonify({
            'success': False,
            'authenticated': False
        }), 401

@app.route('/dashboard')
def dashboard():
    """Performance Dashboard - React.js UI."""
    # Check if user is logged in, if not redirect to login
    if 'user_id' not in session:
        return render_template('login.html', redirect_to='/dashboard')
    return render_template('dashboard.html')

@app.route('/upload', methods=['POST'])
@login_required
def upload_files():
    """Handle file upload and generate report."""
    try:
        # Get property name
        property_name = request.form.get('property_name', 'Property').strip()
        if not property_name:
            property_name = 'Property 1'
        
        # Create session upload folder
        session_id = session.get('session_id')
        if not session_id:
            session_id = str(uuid.uuid4())
            session['session_id'] = session_id
        
        upload_dir = app.config['UPLOAD_FOLDER'] / session_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        documents = []
        images = []
        
        # Support both separate uploads and single mixed upload
        # First, try to get files from 'files' field (single mixed upload)
        if 'files' in request.files:
            files = request.files.getlist('files')
            docs_dir = upload_dir / 'documents'
            imgs_dir = upload_dir / 'images'
            docs_dir.mkdir(exist_ok=True)
            imgs_dir.mkdir(exist_ok=True)
            
            for file in files:
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
                    
                    # Automatically categorize based on file extension
                    if ext in ALLOWED_DOCUMENTS:
                        file_path = docs_dir / filename
                        file.save(file_path)
                        documents.append(str(file_path))
                    elif ext in ALLOWED_IMAGES:
                        file_path = imgs_dir / filename
                        file.save(file_path)
                        images.append(str(file_path))
        
        # Also support separate document and image uploads (backward compatibility)
        if 'documents' in request.files:
            files = request.files.getlist('documents')
            docs_dir = upload_dir / 'documents'
            docs_dir.mkdir(exist_ok=True)
            
            for file in files:
                if file and file.filename and allowed_file(file.filename, ALLOWED_DOCUMENTS):
                    filename = secure_filename(file.filename)
                    file_path = docs_dir / filename
                    file.save(file_path)
                    documents.append(str(file_path))
        
        if 'images' in request.files:
            files = request.files.getlist('images')
            imgs_dir = upload_dir / 'images'
            imgs_dir.mkdir(exist_ok=True)
            
            for file in files:
                if file and file.filename and allowed_file(file.filename, ALLOWED_IMAGES):
                    filename = secure_filename(file.filename)
                    file_path = imgs_dir / filename
                    file.save(file_path)
                    images.append(str(file_path))
        
        if not documents and not images:
            return jsonify({'error': 'Please upload at least one document or image file.'}), 400
        
        # Enable log capture for dashboard
        try:
            log_capture.enable()
            total_files = len(documents) + len(images)
            log_capture.log(f"📤 Files are successfully uploaded!", "SUCCESS")
            log_capture.log(f"   - Total Files: {total_files} file(s)", "INFO")
            log_capture.log(f"   - Documents: {len(documents)} file(s)", "INFO")
            log_capture.log(f"   - Images: {len(images)} file(s)", "INFO")
            log_capture.log(f"   - Property Name: {property_name}", "INFO")
        except:
            pass  # If logging not available, continue anyway
        
        # Generate unique report_id immediately for tracking
        report_id = str(uuid.uuid4())
        user_id = session.get('user_id')
        username = session.get('username')
        
        # Get next job number for this user
        from reports_registry import get_all_reports
        user_reports = get_all_reports(limit=1000, user_id=user_id)
        existing_job_numbers = [r.get('job_number') for r in user_reports if r.get('job_number')]
        next_job_number = max(existing_job_numbers) + 1 if existing_job_numbers else 1
        
        # Create a temporary file path for the report (will be updated when complete)
        temp_output_path = str(upload_dir / f"report_{report_id}.pdf")
        
        # Register report immediately with "processing" status
        register_report(
            report_id=report_id,
            property_name=property_name,
            file_path=temp_output_path,
            property_id=None,
            user_id=user_id,
            username=username,
            status='processing',
            job_number=next_job_number
        )
        
        # Define status callback for logging
        def status_callback(msg):
            # Status updates logged to dashboard
            try:
                log_capture.log(msg, "INFO")
            except:
                pass  # If logging not available, continue anyway
        
        # Add report to sequential processing queue
        # Reports will be processed one at a time in the order they were uploaded
        report_task = {
            'report_id': report_id,
            'documents': documents,
            'images': images,
            'property_name': property_name,
            'upload_dir': upload_dir,
            'job_number': next_job_number,
            'status_callback': status_callback
        }
        
        # Add to queue (FIFO - First In First Out)
        report_queue.put(report_task)
        print(f"[INFO] Report {report_id} (Job {next_job_number}) added to processing queue. Queue size: {report_queue.qsize()}")
        
        # Start worker thread if not already running
        global is_worker_running
        with queue_lock:
            if not is_worker_running:
                is_worker_running = True
                worker_thread = Thread(target=process_report_queue, daemon=True)
                worker_thread.start()
                print("[INFO] Started sequential report processing worker thread")
        
        # Return immediately with report_id - processing happens in background
        response_data = {
            'success': True,
            'message': 'Files uploaded successfully! Report generation started.',
            'report_id': report_id,
            'status': 'processing',
            'property_name': property_name,
            'documents_count': len(documents),
            'images_count': len(images),
            'total_files': len(documents) + len(images),
            'job_number': next_job_number
        }
        
        return jsonify(response_data)
        
    except Exception as gen_error:
        import traceback
        traceback.print_exc()   # ✅ This prints exact file & line number
        error_msg = f"Report generation failed: {str(gen_error)}"
        return jsonify({'error': error_msg, 'success': False}), 500

@app.route('/view')
def view_report():
    """View the generated PDF report in browser."""
    output_pdf = session.get('output_pdf')
    if not output_pdf or not Path(output_pdf).exists():
        return jsonify({'error': 'Report not found. Please generate a report first.'}), 404
    
    return send_file(
        output_pdf,
        as_attachment=False,  # Display in browser instead of downloading
        download_name=Path(output_pdf).name,
        mimetype='application/pdf'
    )

@app.route('/download')
def download_report():
    """Download the generated PDF report."""
    output_pdf = session.get('output_pdf')
    if not output_pdf or not Path(output_pdf).exists():
        return jsonify({'error': 'Report not found. Please generate a report first.'}), 404
    
    return send_file(
        output_pdf,
        as_attachment=True,
        download_name=Path(output_pdf).name,
        mimetype='application/pdf'
    )

@app.route('/status')
def status():
    """Check if report is ready."""
    output_pdf = session.get('output_pdf')
    if output_pdf and Path(output_pdf).exists():
        return jsonify({
            'ready': True,
            'pdf_path': output_pdf,
            'filename': Path(output_pdf).name
        })
    return jsonify({'ready': False})

@app.route('/logs/stream')
def stream_logs():
    """Server-Sent Events endpoint for real-time log streaming."""
    def generate():
        last_count = 0
        try:
            while True:
                logs = get_recent_logs(1000)
                if len(logs) > last_count:
                    # Send new logs
                    for log in logs[last_count:]:
                        try:
                            yield f"data: {json.dumps(log)}\n\n"
                        except Exception as e:
                            print(f"Error encoding log: {e}")
                            continue
                    last_count = len(logs)
                time.sleep(0.3)  # Check every 300ms for faster updates
        except GeneratorExit:
            # Client disconnected
            pass
        except Exception as e:
            print(f"SSE error: {e}")
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no'
    })

@app.route('/logs/recent')
def get_logs():
    """Get recent logs."""
    count = request.args.get('count', 100, type=int)
    logs = get_recent_logs(count)
    return jsonify({'logs': logs})

@app.route('/timings')
def get_function_timings():
    """Get function execution timings."""
    timings = get_timings()
    return jsonify({'timings': timings})

@app.route('/logs/clear', methods=['POST'])
def clear_logs_endpoint():
    """Clear all logs."""
    log_capture.clear_logs()
    clear_timings()
    return jsonify({'success': True, 'message': 'Logs and timings cleared'})

# Reports Registry API endpoints
@app.route('/api/reports', methods=['GET'])
@login_required
def list_reports():
    """Get all reports for the current user only."""
    try:
        limit = request.args.get('limit', 100, type=int)
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({
                'success': False,
                'error': 'User not authenticated',
                'reports': [],
                'count': 0
            }), 401
        
        # Filter reports by current user - only show reports uploaded by this user
        reports = get_all_reports(limit=limit, user_id=user_id)
        
        # Double-check: filter out any reports that don't belong to this user (safety check)
        user_reports = [r for r in reports if r.get('user_id') == user_id]
        
        return jsonify({
            'success': True,
            'reports': user_reports,
            'count': len(user_reports),
            'user_id': user_id
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'reports': [],
            'count': 0
        }), 500

@app.route('/api/reports/<report_id>', methods=['GET'])
@login_required
def get_report_by_id(report_id):
    """Get a specific report by ID."""
    try:
        report = get_report(report_id)
        if report:
            return jsonify({
                'success': True,
                'report': report
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Report not found'
            }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/reports/<report_id>/view', methods=['GET'])
@login_required
def view_report_by_id(report_id):
    """View a report PDF by report ID."""
    try:
        report = get_report(report_id)
        if not report:
            return jsonify({'error': 'Report not found'}), 404
        
        file_path = Path(report['file_path'])
        if not file_path.exists():
            return jsonify({'error': 'Report file not found'}), 404
        
        return send_file(
            file_path,
            as_attachment=False,
            download_name=file_path.name,
            mimetype='application/pdf'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/<report_id>/download', methods=['GET'])
@login_required
def download_report_by_id(report_id):
    """Download a report PDF by report ID."""
    try:
        report = get_report(report_id)
        if not report:
            return jsonify({'error': 'Report not found'}), 404
        
        file_path = Path(report['file_path'])
        if not file_path.exists():
            return jsonify({'error': 'Report file not found'}), 404
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=file_path.name,
            mimetype='application/pdf'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/<report_id>', methods=['DELETE'])
def delete_report_by_id(report_id):
    """Delete a report from the registry."""
    try:
        if delete_report(report_id):
            return jsonify({
                'success': True,
                'message': 'Report deleted successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to delete report'
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def open_browser():
    """Open the default web browser after a short delay to allow server to start."""
    time.sleep(1.5)  # Wait for server to start
    url = "http://127.0.0.1:5001"
    try:
        webbrowser.open(url)
        print(f"✓ Browser opened automatically at {url}")
        print(f"   You can now upload property documents!")
    except Exception as e:
        print(f"⚠ Could not open browser automatically: {e}")
        print(f"   Please manually open: {url}")

if __name__ == '__main__':
    # Ensure upload folder exists
    app.config['UPLOAD_FOLDER'].mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("Starting Property Report Generator Server...")
    print("=" * 60)
    
    # Clear all previous reports and logs on server startup
    print("\n[INFO] Clearing previous reports and logs...")
    try:
        clear_all_reports()
        log_capture.clear_logs()
        clear_timings()
        print("[INFO] ✓ Previous data cleared successfully")
    except Exception as e:
        print(f"[WARNING] Error clearing previous data: {e}")
    
    # Open browser automatically in a separate thread
    # Since we're using use_reloader=False, we don't need to check WERKZEUG_RUN_MAIN
    print("\nOpening browser automatically in 1.5 seconds...")
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()
    
    print("\nServer running at: http://127.0.0.1:5001")
    print("Press CTRL+C to stop the server\n")
    
    # Use threaded=True to handle multiple requests better
    # Set use_reloader=False to prevent code reloading during report generation
    app.run(debug=True, host='127.0.0.1', port=5001, use_reloader=False, threaded=True)

