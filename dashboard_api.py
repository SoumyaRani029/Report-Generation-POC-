"""
Flask REST API endpoints for Dashboard.
Provides JSON data for React.js frontend.
"""
import re
from flask import Blueprint, jsonify, request
from performance_tracker import get_timings, get_recent_logs, log_capture, clear_timings

dashboard_api = Blueprint('dashboard_api', __name__, url_prefix='/api/dashboard')

def determine_progress(logs):
    """Determine current progress based on log messages."""
    if not logs:
        return {'step': 0, 'percent': 0, 'status': 'Waiting to start...'}
    
    recent_messages = ' '.join([log.get('message', '') for log in logs[-30:]])
    recent_messages_lower = recent_messages.lower()
    
    # Only mark as complete when we see VERY specific completion messages
    # Check for actual completion indicators, not just "Report generated" which might appear early
    completion_indicators = [
        'done! report saved to',
        'done! report saved',
        'report saved to',
        'pdf report generated successfully',
        'report generation completed',
        '✅ done! report saved',
        '✅ all property data saved',
        'completed: generate_report_from_files',
        'report generated successfully:',
        'all property data saved to property_valuations.db'
    ]
    
    is_complete = any(indicator in recent_messages_lower for indicator in completion_indicators)
    
    # Also check if we're still processing - if we see processing messages, don't mark as complete
    # But exclude completion messages from this check - only check last few logs
    processing_indicators = [
        'extracting',
        'sending',
        'analyzing',
        'processing',
        'generating',
        'building',
        'waiting for llm',
        'starting:',
        'running ocr'
    ]
    
    # Check only the last few logs for processing (not all recent messages)
    # This avoids false positives from earlier processing messages
    last_few_logs = logs[-3:] if len(logs) >= 3 else logs
    last_few_messages = ' '.join([log.get('message', '') for log in last_few_logs]).lower()
    
    # Don't consider it processing if we see completion messages in recent logs
    has_completion_in_recent = any(indicator in last_few_messages for indicator in completion_indicators)
    
    is_still_processing = False
    if not has_completion_in_recent:
        # Only check for processing if we don't have completion messages
        is_still_processing = any(indicator in last_few_messages for indicator in processing_indicators)
    
    if is_complete and not is_still_processing:
        return {'step': 6, 'percent': 100, 'status': 'Report Generated ✅'}
    elif 'Comparable' in recent_messages or 'comparable' in recent_messages or 'finding similar' in recent_messages_lower:
        return {'step': 5, 'percent': 83, 'status': 'Generating Comparables...'}
    elif 'Property saved to database' in recent_messages or 'Saving LLM-extracted' in recent_messages or 'saved to sqlite' in recent_messages_lower:
        return {'step': 4, 'percent': 66, 'status': 'Saving to Database...'}
    elif 'LLM' in recent_messages or 'GPT-4' in recent_messages or 'Parsing LLM' in recent_messages or 'sending data to llm' in recent_messages_lower or 'waiting for llm response' in recent_messages_lower:
        return {'step': 3, 'percent': 50, 'status': 'LLM Analysis...'}
    elif 'Extracted text' in recent_messages or 'extracting text' in recent_messages or 'extracting from' in recent_messages_lower:
        return {'step': 2, 'percent': 33, 'status': 'Extracting Text...'}
    elif 'uploaded successfully' in recent_messages or 'Property documents' in recent_messages:
        return {'step': 1, 'percent': 16, 'status': 'Files Uploaded ✅'}
    else:
        return {'step': 0, 'percent': 0, 'status': 'Initializing...'}

@dashboard_api.route('/logs', methods=['GET'])
def get_logs():
    """Get logs as JSON."""
    count = request.args.get('count', 100, type=int)
    logs = get_recent_logs(count)
    return jsonify({
        'success': True,
        'logs': logs,
        'count': len(logs)
    })

@dashboard_api.route('/timings', methods=['GET'])
def get_timings_api():
    """Get function timings as JSON."""
    timings = get_timings()
    total_time = sum(timing['total'] for timing in timings.values()) if timings else 0
    
    return jsonify({
        'success': True,
        'timings': timings,
        'total_time': round(total_time, 2),
        'function_count': len(timings)
    })

@dashboard_api.route('/progress', methods=['GET'])
def get_progress():
    """Get progress status as JSON."""
    logs = get_recent_logs(200)
    progress = determine_progress(logs)
    
    return jsonify({
        'success': True,
        'progress': progress
    })

@dashboard_api.route('/stats', methods=['GET'])
def get_stats():
    """Get all dashboard statistics."""
    timings = get_timings()
    logs = get_recent_logs(100)
    
    # Enhance logs with duration information from timings
    enhanced_logs = []
    from datetime import datetime as dt
    
    # Helper function to parse timestamp and calculate time difference
    def parse_timestamp(ts_str):
        """Parse timestamp string like '15:05:10.543' to seconds since midnight."""
        try:
            if not ts_str:
                return None
            # Try parsing HH:MM:SS.mmm format
            if '.' in ts_str:
                time_part, ms_part = ts_str.rsplit('.', 1)
                h, m, s = map(int, time_part.split(':'))
                ms = int(ms_part[:3]) if len(ms_part) >= 3 else 0
                return h * 3600 + m * 60 + s + ms / 1000.0
            else:
                # Try HH:MM:SS format
                parts = ts_str.split(':')
                if len(parts) == 3:
                    h, m, s = map(int, parts)
                    return h * 3600 + m * 60 + s
                elif len(parts) == 2:
                    m, s = map(int, parts)
                    return m * 60 + s
        except:
            return None
    
    def calculate_time_diff(log1, log2):
        """Calculate time difference between two logs in milliseconds."""
        ts1_str = log1.get('timestamp', '') or log1.get('datetime', '')
        ts2_str = log2.get('timestamp', '') or log2.get('datetime', '')
        
        # If datetime is available, use it (more reliable)
        if not ts1_str and log1.get('datetime'):
            try:
                from datetime import datetime
                dt1 = datetime.fromisoformat(log1['datetime'].replace('Z', '+00:00'))
                dt2 = datetime.fromisoformat(log2.get('datetime', log1['datetime']).replace('Z', '+00:00'))
                diff = (dt2 - dt1).total_seconds() * 1000
                return max(0, diff)
            except:
                pass
        
        time1 = parse_timestamp(ts1_str)
        time2 = parse_timestamp(ts2_str)
        
        if time1 is not None and time2 is not None:
            # Calculate difference (handle day rollover)
            if time2 < time1:
                # Assume next day (or very small negative due to rounding)
                # If difference is very small negative, it's likely rounding error
                if abs(time2 - time1) < 1:
                    diff = abs(time2 - time1)
                else:
                    # Assume next day
                    diff = (86400 - time1) + time2
            else:
                diff = time2 - time1
            return max(0, diff * 1000)  # Convert to milliseconds, ensure non-negative
        return None
    
    for i, log in enumerate(logs):
        log_entry = log.copy() if isinstance(log, dict) else {
            'timestamp': log.get('timestamp', '') if isinstance(log, dict) else '',
            'message': log.get('message', str(log)) if isinstance(log, dict) else str(log),
            'level': log.get('level', 'info') if isinstance(log, dict) else 'info',
            'datetime': log.get('datetime', '') if isinstance(log, dict) else ''
        }
        
        message = log_entry.get('message', '')
        duration_ms = None
        
        # Method 1: Extract duration directly from "Completed" or "Failed" log messages
        # Pattern: "✅ Completed: function_name (2.45s)" or "❌ Failed: function_name (1.23s)"
        completed_match = re.search(r'Completed:\s*[^(]+\(([\d.]+)s\)', message)
        failed_match = re.search(r'Failed:\s*[^(]+\(([\d.]+)s\)', message)
        
        if completed_match:
            duration_ms = float(completed_match.group(1)) * 1000  # Convert to milliseconds
        elif failed_match:
            duration_ms = float(failed_match.group(1)) * 1000
        
        # Method 2: For "Starting" logs, find the matching "Completed" log
        if not duration_ms and 'Starting:' in message:
            # Extract function name from "Starting: function_name"
            func_match = re.search(r'Starting:\s*(.+)', message, re.IGNORECASE)
            if func_match:
                func_name = func_match.group(1).strip()
                # Look ahead for matching "Completed" log
                for j in range(i + 1, min(i + 50, len(logs))):  # Check next 50 logs
                    next_log = logs[j] if isinstance(logs[j], dict) else {'message': str(logs[j])}
                    next_msg = next_log.get('message', '')
                    # Check if this is the matching completed log
                    if f'Completed: {func_name}' in next_msg or f'Completed: {func_name} (' in next_msg:
                        # Extract duration from completed message
                        comp_match = re.search(r'\(([\d.]+)s\)', next_msg)
                        if comp_match:
                            duration_ms = float(comp_match.group(1)) * 1000
                        break
        
        # Method 3: Match with timing data by function name
        if not duration_ms:
            message_lower = message.lower()
            for func_name, timing_data in timings.items():
                func_name_lower = func_name.lower()
                # Check if log message contains function name
                if func_name_lower in message_lower:
                    # Use the most recent timing for this function
                    if 'last' in timing_data and 'duration' in timing_data['last']:
                        duration_ms = timing_data['last']['duration'] * 1000
                        break
                    elif 'average' in timing_data:
                        duration_ms = timing_data['average'] * 1000
                        break
        
        # Method 4: Calculate time difference from previous log (for status messages)
        if not duration_ms and i > 0:
            # Look for operation start patterns
            start_patterns = [
                r'📊\s*Initializing',
                r'📄\s*Extracting',
                r'🤖\s*Sending',
                r'💾\s*Saving',
                r'🔍\s*Finding',
                r'📝\s*Generating',
                r'✅\s*Saved',
                r'✅\s*Extracted',
                r'✅\s*Generated',
                r'✅\s*Completed',
                r'💾\s*Saved',
            ]
            
            # Check if current log is a completion/result log
            is_completion = any(re.search(pattern, message, re.IGNORECASE) for pattern in [
                r'✅\s*Saved',
                r'✅\s*Extracted',
                r'✅\s*Generated',
                r'✅\s*Completed',
                r'💾\s*Saved',
                r'📊\s*Database.*ready',
                r'📁\s*Database.*ready',
            ])
            
            if is_completion:
                # Look backwards for the start of this operation
                for j in range(i - 1, max(-1, i - 20), -1):  # Check previous 20 logs
                    prev_log = logs[j] if isinstance(logs[j], dict) else {'message': str(logs[j]), 'timestamp': ''}
                    prev_msg = prev_log.get('message', '')
                    
                    # Check if previous log is a start of operation
                    is_start = any(re.search(pattern, prev_msg, re.IGNORECASE) for pattern in start_patterns)
                    
                    if is_start:
                        # Calculate time difference
                        time_diff = calculate_time_diff(prev_log, log_entry)
                        if time_diff and time_diff > 0:
                            duration_ms = time_diff
                            break
        
        # Method 5: ALWAYS calculate time difference from previous log (primary fallback)
        # This ensures every log gets a processing time - NO CONDITIONS
        if not duration_ms and i > 0:
            prev_log = logs[i - 1] if isinstance(logs[i - 1], dict) else {'timestamp': '', 'message': str(logs[i - 1])}
            time_diff = calculate_time_diff(prev_log, log_entry)
            # Use any positive duration, even milliseconds (less than 5 minutes to avoid day rollover issues)
            if time_diff is not None and time_diff >= 0 and time_diff < 300000:  # Less than 5 minutes
                duration_ms = time_diff
        
        # Method 6: For logs without duration, calculate from next log (for start operations)
        # This helps identify when an operation starts and how long until the next step
        if not duration_ms and i < len(logs) - 1:
            next_log = logs[i + 1] if isinstance(logs[i + 1], dict) else {'timestamp': '', 'message': str(logs[i + 1])}
            time_diff = calculate_time_diff(log_entry, next_log)
            # Use if it's a reasonable duration and this looks like a start operation
            if time_diff and 0 < time_diff < 300000:
                # Check if this log looks like it starts an operation
                start_keywords = ['copying', 'extracting', 'processing', 'running', 'step', 'page']
                message_lower = message.lower()
                if any(keyword in message_lower for keyword in start_keywords):
                    duration_ms = time_diff
        
        # FINAL FALLBACK: If still no duration and not the first log, force calculate from previous
        # This ensures EVERY log (except first) has a duration
        if duration_ms is None and i > 0:
            prev_log = logs[i - 1] if isinstance(logs[i - 1], dict) else {'timestamp': '', 'message': str(logs[i - 1])}
            time_diff = calculate_time_diff(prev_log, log_entry)
            if time_diff is not None:
                # Accept even 0 or very small values
                if time_diff >= 0 and time_diff < 300000:
                    duration_ms = time_diff
        
        # Ensure duration_ms is set (even if 0 or very small)
        # Convert to float and round to 3 decimal places for precision
        if duration_ms is not None:
            duration_ms = round(float(duration_ms), 3)
        
        log_entry['duration_ms'] = duration_ms
        enhanced_logs.append(log_entry)
    
    total_time = sum(timing['total'] for timing in timings.values()) if timings else 0
    function_count = len(timings)
    log_count = len(enhanced_logs)
    progress = determine_progress(logs)
    
    return jsonify({
        'success': True,
        'stats': {
            'total_time': round(total_time, 2),
            'function_count': function_count,
            'log_count': log_count,
            'progress': progress,
            'timings': timings,
            'logs': enhanced_logs
        }
    })

@dashboard_api.route('/clear', methods=['POST'])
def clear_data():
    """Clear logs and timings."""
    try:
        log_capture.clear_logs()
        clear_timings()
        return jsonify({
            'success': True,
            'message': 'Logs and timings cleared'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

