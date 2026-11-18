import subprocess
import os

# Run the three verification steps
results = {}

# Step 1: pitchfork status
try:
    result = subprocess.run(
        ['/home/toxic/pens/Pens/bin/pitchfork', 'status', 'Pens/Pens-reconcile-watch'],
        capture_output=True, text=True, timeout=10
    )
    results['pitchfork_status'] = result.stdout.strip()
    results['pitchfork_stderr'] = result.stderr.strip()
    results['pitchfork_rc'] = result.returncode
except Exception as e:
    results['pitchfork_error'] = str(e)

# Step 2: tail log and find most recent CHECK line
try:
    result = subprocess.run(
        ['tail', '-n', '5', '/home/toxic/pens/Pens/var/log/Pens-reconcile.log'],
        capture_output=True, text=True, timeout=10
    )
    results['tail_output'] = result.stdout.strip()
    results['tail_stderr'] = result.stderr.strip()
    results['tail_rc'] = result.returncode
    
    # Find the most recent CHECK line
    check_lines = [line for line in result.stdout.strip().split('\n') if 'CHECK' in line]
    results['most_recent_check'] = check_lines[-1] if check_lines else "No CHECK line found in last 5 lines"
except Exception as e:
    results['tail_error'] = str(e)

# Step 3: Check for drift entries newer than 2026-09-30
try:
    result = subprocess.run(
        ['cat', '/home/toxic/pens/Pens/var/log/Pens-reconcile.log'],
        capture_output=True, text=True, timeout=10
    )
    log_content = result.stdout
    
    # Look for drift entries with dates after 2026-09-30
    import re
    # Pattern to match dates in log entries (assuming format like 2026-10-01 or similar)
    date_pattern = r'(\d{4}-\d{2}-\d{2})'
    drift_entries_newer = []
    
    for line in log_content.split('\n'):
        if 'drift' in line.lower() or 'DRIFT' in line:
            dates = re.findall(date_pattern, line)
            for date_str in dates:
                if date_str > '2026-09-30':
                    drift_entries_newer.append(line)
                    break
    
    results['drift_entries_newer_than_2026_09_30'] = drift_entries_newer
    results['has_newer_drift'] = len(drift_entries_newer) > 0
except Exception as e:
    results['drift_check_error'] = str(e)

# Write report
report_path = 'drift-watch-report.md'
with open(report_path, 'w') as f:
    f.write('# Drift-Watch Restoration Verification Report\n\n')
    f.write('## Task: [no-corral] T1 re-run (scout): verify the drift-watch restoration on yote\n\n')
    
    f.write('### 1. Pitchfork Status\n')
    f.write(f'