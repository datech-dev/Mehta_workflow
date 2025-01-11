from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash, Response, send_file

import os
import json
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_session import Session
import xlsxwriter
import io
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart



app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_COOKIE_SECURE'] = False  # Store sessions on the filesystem
Session(app)

# Configurations
DATA_FOLDER = './data'
USER_FILE = os.path.join(DATA_FOLDER, 'users.json')
TASK_FILE = os.path.join(DATA_FOLDER, 'tasks.json')

# Outlook SMTP credentials
SMTP_SERVER = 'smtp.hostinger.com'  # Replace with your SMTP server
SMTP_PORT = 587 # Use 587 for TLS or 465 for SSL
EMAIL_ADDRESS = 'contact@datechnologies.cloud'  # Replace with your email
EMAIL_PASSWORD = 'N00bl337py*'  # Replace with your email password


def send_email(subject, recipient, message_body):
    """Send an email using custom domain SMTP."""
    try:
        message = MIMEMultipart()
        message['From'] = EMAIL_ADDRESS
        message['To'] = recipient
        message['Subject'] = subject
        message.attach(MIMEText(message_body, 'plain'))

        # Connect to the SMTP server
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()  # Start TLS encryption
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)

        # Send the email
        server.send_message(message)
        server.quit()
        print(f"Email sent to {recipient}")
    except Exception as e:
        print(f"Failed to send email: {e}")


def load_users():
    """Load the users from the JSON file."""
    try:
        with open(USER_FILE, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return []  # If the file doesn't exist, return an empty list

def get_user_by_username(username):
    """Fetch a user by their username."""
    users = load_users()
    for user in users:                          
        if user['username'] == username:
            return user
    return None


# Initialize storage files
os.makedirs(DATA_FOLDER, exist_ok=True)
if not os.path.exists(USER_FILE):
    with open(USER_FILE, 'w') as f:
        json.dump([], f)
if not os.path.exists(TASK_FILE):
    with open(TASK_FILE, 'w') as f:
        json.dump([], f)


# Helper Functions
def load_json(file_path):
    try:
        with open(file_path, 'r') as file:
            data = json.load(file)
            print(f"Loaded users data: {data}")  # Debugging log
            return data
    except Exception as e:
        print(f"Error loading file: {e}")  # Log if there's an error
        return []


def save_json(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)


# Role-based route decorator
def role_required(role):
    def decorator(func):
        def wrapper(*args, **kwargs):
            if 'user' not in session or session.get('role') != role:
                flash("Access denied: Insufficient permissions.")
                return redirect(url_for('dashboard'))
            return func(*args, **kwargs)
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator


@app.route('/')
def home():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('register'))


from werkzeug.security import generate_password_hash

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.form
        users = load_json(USER_FILE)

        # Check if the username already exists
        if any(user['username'] == data['username'] for user in users):
            return jsonify({"error": "Username already exists"}), 400

        # Create a new user with email and hashed password
        new_user = {
            "username": data['username'],
            "email": data['email'],  # Collect email from registration form
            "password": generate_password_hash(data['password']),
            "role": data['role']
        }
        users.append(new_user)
        save_json(USER_FILE, users)
        return jsonify({"message": "User registered successfully"}), 201

    return render_template('register.html')



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    else:
        data = request.form
        print("Login data received:", data)  # Debugging
        
        users = load_json(USER_FILE)
        user = next((u for u in users if u['username'] == data['username']), None)
        print("User found in database:", user)  # Debugging

        if user and check_password_hash(user['password'], data['password']):
            session['user'] = user['username']
            session['role'] = user['role']
            print("Login successful, session set:", session)  # Debugging
            flash("Login successful!", "success")
            return redirect(url_for('dashboard'))
        else:
            print("Invalid login attempt.")  # Debugging
            flash("Invalid username or password!", "danger")
            return redirect(url_for('login'))




@app.route('/logout')
def logout():
    session.clear()
    session.pop('user', None)
    session.pop('role', None)
    return redirect(url_for('login'))


@app.route('/get_tasks', methods=['GET'])
def get_tasks():
    username = session.get('user')
    role = session.get('role')
    tasks = load_json(TASK_FILE)  # Load the task data from the JSON file

    # Filter tasks based on the role
    if role == 'Admin':
        user_tasks = tasks  # Admins see all tasks
    elif role == 'Employee':
        user_tasks = [task for task in tasks if task['assigned_to'] == username]  # Employees see only their tasks
    else:
        user_tasks = []  # No tasks for other roles (if any)

    return jsonify(user_tasks)



@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    tasks = load_json(TASK_FILE)  # Load all tasks from JSON

    # Calculate time left for each task
    now = datetime.now()
    for task in tasks:
        if 'deadline' in task and task['deadline']:
            try:
                deadline = datetime.strptime(task['deadline'], '%Y-%m-%d %H:%M:%S')
                time_difference = deadline - now
                if time_difference.total_seconds() > 0:
                    task['time_left'] = f"{time_difference.days} days, {time_difference.seconds // 3600} hours"
                else:
                    task['time_left'] = "Deadline passed"
            except ValueError:
                task['time_left'] = "Invalid deadline format"
        else:
            task['time_left'] = "No deadline"

    role = session.get('role')
    return render_template('dashboard.html', role=role, tasks=tasks)



from datetime import datetime, timedelta

@app.route('/create_task', methods=['GET', 'POST'])
@role_required('Admin')  # Ensure only admins can access this page
def create_task():
    if request.method == 'POST':
        data = request.form

        # Get the form fields
        task_name = data.get('name')
        task_description = data.get('description')
        task_deadline = data.get('deadline')
        assigned_to = data.get('assigned_to')  # This will be the username of the assignee
        unique_task_id = f"{task_name}_{task_deadline}_{assigned_to}"  # Generate a unique identifier

        # Check if the required fields are present
        if not task_name or not task_description or not task_deadline or not assigned_to:
            flash("All fields are required!", "error")
            return redirect(url_for('create_task'))

        # Parse the deadline into a standardized format
        try:
            parsed_deadline = datetime.strptime(task_deadline, '%Y-%m-%dT%H:%M')
            formatted_deadline = parsed_deadline.strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            flash("Invalid deadline format!", "error")
            return redirect(url_for('create_task'))

        tasks = load_json(TASK_FILE)

        # Check if a task with the same unique identifier already exists
        for task in tasks:
            if task.get('unique_id') == unique_task_id:
                flash("This task already exists.", "error")
                return redirect(url_for('create_task'))

        # Find the assigned user by their username
        user = get_user_by_username(assigned_to)
        if not user:
            flash("User not found!", "error")
            return redirect(url_for('create_task'))

        # Calculate the time left until the deadline
        # Calculate the time left until the deadline
        now = datetime.utcnow()
        time_difference = parsed_deadline - now

        if time_difference.total_seconds() > 0:
            total_seconds = int(time_difference.total_seconds())
            days_left = total_seconds // (24 * 3600)
            time_left = f"{days_left} days left until the deadline"
        else:
            time_left = "Deadline has already passed"


        new_task = {
            "id": len(tasks) + 1,
            "unique_id": unique_task_id,  # Add the unique identifier to the task
            "name": task_name,
            "description": task_description,
            "created_by": session['user'],
            "assigned_to": assigned_to,
            "deadline": formatted_deadline,  # Use the formatted deadline
            "comments": [],
            "blocking_reasons": [],
            "files": [],
            "stage": "Allotted",
            "creation_time": datetime.utcnow().isoformat(),
        }

        tasks.append(new_task)
        save_json(TASK_FILE, tasks)

        # Send email notification to the assigned user
        subject = f"New Task Assigned: {task_name}"
        message_body = f"Hello {user['username']},\n\n" \
                       f"You have been assigned a new task:\n" \
                       f"Task Name: {task_name}\n" \
                       f"Description: {task_description}\n" \
                       f"Deadline: {task_deadline}\n" \
                       f"Time Left: {time_left}\n\n" \
                       f"Best regards,\nTask Manager Team"
        send_email(subject, user['email'], message_body)

        flash("Task created and email sent successfully!")
        return redirect(url_for('dashboard'))

    # Load the list of users from your data source
    users = load_users()
    return render_template('create_task.html', users=users)





@app.route('/assign_task/<int:task_id>', methods=['POST'])
@role_required('Admin')  # Ensure only admins can assign tasks
def assign_task(task_id):
    tasks = load_json(TASK_FILE)
    data = request.json
    for task in tasks:
        if task['id'] == task_id:
            task['assigned_to'] = data['assigned_to']
            task['stage'] = "Assigned"
            task['assignment_time'] = datetime.utcnow().isoformat()

            # Find the user by their username
            user = get_user_by_username(data['assigned_to'])
            if not user:
                return jsonify({"error": "User not found"}), 404

            save_json(TASK_FILE, tasks)

            # Send email notification to the assigned user
            subject = f"Task Update: {task['name']}"
            message_body = f"Hello {user['username']},\n\n" \
                           f"You have been assigned a task:\n" \
                           f"Task Name: {task['name']}\n" \
                           f"Description: {task['description']}\n" \
                           f"Deadline: {task['deadline']}\n\n" \
                           f"Best regards,\nTask Manager Team"
            send_email(subject, user['email'], message_body)

            return jsonify({"message": "Task assigned and email sent successfully"}), 200
    return jsonify({"error": "Task not found"}), 404


@app.route('/update_task_status/<int:task_id>', methods=['POST'])
@role_required('employee')
def update_task_status(task_id):
    data = request.json
    tasks = load_json(TASK_FILE)
    for task in tasks:
        if task['id'] == task_id:
            if task['assigned_to'] != session['user']:
                return jsonify({"error": "Unauthorized action"}), 403
            
            # Update stage and add blocking reason if provided
            task['stage'] = data['stage']
            if data['stage'] == "Blocked":
                task['blocking_reasons'].append({
                    "reason": data['reason'],
                    "time": datetime.utcnow().isoformat()
                })
            save_json(TASK_FILE, tasks)
            return jsonify({"message": "Task status updated successfully"}), 200
    return jsonify({"error": "Task not found"}), 404




from flask import session, flash, redirect, url_for
from datetime import datetime

@app.route('/view_task/<int:task_id>', methods=['GET', 'POST'])
def view_task(task_id):
    tasks = load_json(TASK_FILE)
    task = next((task for task in tasks if task['id'] == task_id), None)

    if not task:
        flash("Task not found!", "danger")
        return redirect(url_for('dashboard'))

    # Initialize `stage_changes`, `comments`, and `invoice_status_history` if not present
    if 'stage_changes' not in task:
        task['stage_changes'] = []
    if 'comments' not in task:
        task['comments'] = []
    if 'invoice_status_history' not in task:
        task['invoice_status_history'] = []

    # Calculate time left until the deadline
    time_left = None
    if 'deadline' in task and task['deadline']:
        try:
            deadline = datetime.strptime(task['deadline'], '%Y-%m-%d %H:%M:%S')
            now = datetime.utcnow()
            time_difference = deadline - now
            if time_difference.total_seconds() > 0:
                time_left = {
                    'days': time_difference.days,
                    'hours': time_difference.seconds // 3600,
                    'minutes': (time_difference.seconds % 3600) // 60,
                }
            else:
                time_left = "Deadline has passed."
        except ValueError:
            time_left = "Invalid deadline format."

    if request.method == 'POST':
        new_status = request.form.get('status')
        new_comment = request.form.get('comment')
        new_invoice_status = request.form.get('invoice_status')
        user_role = session.get('role')
        user_name = session.get('user')

        # Ensure only admins can change the task stage
        if new_status and user_role != 'Admin':
            flash("You do not have permission to change the task stage.", "danger")
            return redirect(url_for('view_task', task_id=task_id))

        # Add a stage change if an admin is updating it
        if new_status and new_status != task['stage']:
            change_entry = {
                'stage': new_status,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'comment': new_comment or "No comment provided",
                'commented_by': user_name,
            }
            task['stage_changes'].append(change_entry)
            task['stage'] = new_status

        # Add a comment for admins or employees
        if new_comment:
            comment_entry = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'comment': new_comment,
                'commented_by': user_name,
            }
            task['comments'].append(comment_entry)

        # Handle invoice status updates (accessible to both admins and employees)
        if new_invoice_status:
            invoice_status_entry = {
                'invoice_status': new_invoice_status,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'commented_by': user_name,
            }
            task['invoice_status_history'].append(invoice_status_entry)

        # Save the updated task back to the JSON file
        save_json(TASK_FILE, tasks)
        flash("Task updated successfully!", "success")
        return redirect(url_for('view_task', task_id=task_id))

    latest_invoice_status = (
        task['invoice_status_history'][-1]['invoice_status']
        if task['invoice_status_history']
        else "No status provided"
    )

    return render_template(
        'view_task.html',
        task=task,
        time_left=time_left,
        latest_invoice_status=latest_invoice_status,
        is_admin=(session.get('role') == 'Admin'),
    )



@app.route('/export_tasks', methods=['GET'])
def export_tasks():
    tasks = load_json(TASK_FILE)
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})

    # Create sheets
    stage_changes_sheet = workbook.add_worksheet("Stage Changes")
    invoice_status_sheet = workbook.add_worksheet("Invoice Status Updates")

    # Write headers for stage changes sheet
    stage_changes_headers = [
        'Task ID', 'Task Name', 'Description', 'Created By', 'Assigned To',
        'Deadline', 'Creation Time', 'Current Stage',
        'Stage Change', 'Stage Timestamp', 'Stage Comment', 'Commented By'
    ]
    for col_num, header in enumerate(stage_changes_headers):
        stage_changes_sheet.write(0, col_num, header)

    # Write headers for invoice status sheet
    invoice_status_headers = [
        'Task ID', 'Task Name', 'Description', 'Created By', 'Assigned To',
        'Deadline', 'Creation Time', 'Invoice Status', 'Invoice Status Timestamp',
        'Invoice Status Commented By'
    ]
    for col_num, header in enumerate(invoice_status_headers):
        invoice_status_sheet.write(0, col_num, header)

    # Populate stage changes sheet
    stage_row = 1
    for task in tasks:
        task_id = task.get('id', '')
        task_name = task.get('name', '')
        description = task.get('description', '')
        created_by = task.get('created_by', '')
        assigned_to = task.get('assigned_to', '')
        deadline = task.get('deadline', '')
        creation_time = task.get('creation_time', '')
        current_stage = task.get('stage', '')

        stage_changes = task.get('stage_changes', [])
        if not stage_changes:  # Include tasks without stage changes
            stage_changes = [{}]

        for stage_change in stage_changes:
            stage_changes_sheet.write(stage_row, 0, task_id)
            stage_changes_sheet.write(stage_row, 1, task_name)
            stage_changes_sheet.write(stage_row, 2, description)
            stage_changes_sheet.write(stage_row, 3, created_by)
            stage_changes_sheet.write(stage_row, 4, assigned_to)
            stage_changes_sheet.write(stage_row, 5, deadline)
            stage_changes_sheet.write(stage_row, 6, creation_time)
            stage_changes_sheet.write(stage_row, 7, current_stage)
            stage_changes_sheet.write(stage_row, 8, stage_change.get('stage', ''))
            stage_changes_sheet.write(stage_row, 9, stage_change.get('timestamp', ''))
            stage_changes_sheet.write(stage_row, 10, stage_change.get('comment', ''))
            stage_changes_sheet.write(stage_row, 11, stage_change.get('commented_by', ''))
            stage_row += 1

    # Populate invoice status updates sheet
    invoice_row = 1
    for task in tasks:
        task_id = task.get('id', '')
        task_name = task.get('name', '')
        description = task.get('description', '')
        created_by = task.get('created_by', '')
        assigned_to = task.get('assigned_to', '')
        deadline = task.get('deadline', '')
        creation_time = task.get('creation_time', '')

        invoice_status_history = task.get('invoice_status_history', [])
        if not invoice_status_history:  # Include tasks without invoice updates
            invoice_status_history = [{}]

        for invoice_status in invoice_status_history:
            invoice_status_sheet.write(invoice_row, 0, task_id)
            invoice_status_sheet.write(invoice_row, 1, task_name)
            invoice_status_sheet.write(invoice_row, 2, description)
            invoice_status_sheet.write(invoice_row, 3, created_by)
            invoice_status_sheet.write(invoice_row, 4, assigned_to)
            invoice_status_sheet.write(invoice_row, 5, deadline)
            invoice_status_sheet.write(invoice_row, 6, creation_time)
            invoice_status_sheet.write(invoice_row, 7, invoice_status.get('invoice_status', ''))
            invoice_status_sheet.write(invoice_row, 8, invoice_status.get('timestamp', ''))
            invoice_status_sheet.write(invoice_row, 9, invoice_status.get('commented_by', ''))
            invoice_row += 1

    workbook.close()
    output.seek(0)

    # Send the Excel file as a response
    return Response(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment;filename=tasks_report.xlsx"}
    )




from flask import Response
import xlsxwriter
import io
from datetime import datetime

from datetime import datetime

@app.route('/daily_report', methods=['GET'])
@role_required('Admin')  # Ensure only admins can access this report
def daily_report():
    tasks = load_json(TASK_FILE)
    today = datetime.utcnow().strftime('%Y-%m-%d')  # Current date in YYYY-MM-DD format

    # Filter tasks based on today's creation date or updates
    filtered_tasks = []
    for task in tasks:
        # Check if the task was created today
        if task['creation_time'].startswith(today):
            filtered_tasks.append(task)
            continue

        # Check if there are comments added today
        for comment in task.get('comments', []):
            if comment['timestamp'].startswith(today):
                filtered_tasks.append(task)
                break

        # Check if there are invoice status updates today
        for invoice_status in task.get('invoice_status_history', []):
            if invoice_status['timestamp'].startswith(today):
                filtered_tasks.append(task)
                break

    # Remove duplicates (if a task is added multiple times from different checks)
    filtered_tasks = {task['id']: task for task in filtered_tasks}.values()

    # Generate Excel file
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet("Daily Report")

    # Write headers
    headers = [
        "Task ID", "Task Name", "Description", "Created By", "Assigned To",
        "Stage", "Deadline", "Creation Time", "Comment Timestamp", "Commented By",
        "Comment Text", "Invoice Status Timestamp", "Invoice Status", "Invoice Commented By"
    ]
    for col_num, header in enumerate(headers):
        worksheet.write(0, col_num, header)

    # Populate rows
    row_num = 1
    for task in filtered_tasks:
        # Format dates as dd/mm/yyyy
        creation_time = format_date(task.get('creation_time', ''))
        deadline = format_date(task.get('deadline', ''))

        # Write task creation row
        worksheet.write(row_num, 0, task['id'])
        worksheet.write(row_num, 1, task['name'])
        worksheet.write(row_num, 2, task['description'])
        worksheet.write(row_num, 3, task['created_by'])
        worksheet.write(row_num, 4, task['assigned_to'])
        worksheet.write(row_num, 5, task['stage'])
        worksheet.write(row_num, 6, deadline)
        worksheet.write(row_num, 7, creation_time)
        worksheet.write(row_num, 8, "")  # No comment timestamp for this row
        worksheet.write(row_num, 9, "")  # No commented_by for this row
        worksheet.write(row_num, 10, "")  # No comment text for this row
        worksheet.write(row_num, 11, "")  # No invoice timestamp for this row
        worksheet.write(row_num, 12, "")  # No invoice status for this row
        worksheet.write(row_num, 13, "")  # No invoice commented_by for this row
        row_num += 1

        # Write rows for today's comments
        for comment in task.get('comments', []):
            if comment['timestamp'].startswith(today):
                comment_timestamp = format_date(comment['timestamp'])
                worksheet.write(row_num, 0, task['id'])
                worksheet.write(row_num, 1, task['name'])
                worksheet.write(row_num, 2, task['description'])
                worksheet.write(row_num, 3, task['created_by'])
                worksheet.write(row_num, 4, task['assigned_to'])
                worksheet.write(row_num, 5, task['stage'])
                worksheet.write(row_num, 6, deadline)
                worksheet.write(row_num, 7, creation_time)
                worksheet.write(row_num, 8, comment_timestamp)  # Comment timestamp
                worksheet.write(row_num, 9, comment['commented_by'])  # Commented by
                worksheet.write(row_num, 10, comment['comment'])  # Comment text
                worksheet.write(row_num, 11, "")  # No invoice timestamp for this row
                worksheet.write(row_num, 12, "")  # No invoice status for this row
                worksheet.write(row_num, 13, "")  # No invoice commented_by for this row
                row_num += 1

        # Write rows for today's invoice status updates
        for invoice_status in task.get('invoice_status_history', []):
            if invoice_status['timestamp'].startswith(today):
                invoice_timestamp = format_date(invoice_status['timestamp'])
                worksheet.write(row_num, 0, task['id'])
                worksheet.write(row_num, 1, task['name'])
                worksheet.write(row_num, 2, task['description'])
                worksheet.write(row_num, 3, task['created_by'])
                worksheet.write(row_num, 4, task['assigned_to'])
                worksheet.write(row_num, 5, task['stage'])
                worksheet.write(row_num, 6, deadline)
                worksheet.write(row_num, 7, creation_time)
                worksheet.write(row_num, 8, "")  # No comment timestamp for this row
                worksheet.write(row_num, 9, "")  # No commented_by for this row
                worksheet.write(row_num, 10, "")  # No comment text for this row
                worksheet.write(row_num, 11, invoice_timestamp)  # Invoice timestamp
                worksheet.write(row_num, 12, invoice_status['invoice_status'])  # Invoice status
                worksheet.write(row_num, 13, invoice_status.get('commented_by', ''))  # Invoice commented_by
                row_num += 1

    workbook.close()
    output.seek(0)

    # Send the file as a response
    return Response(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment;filename=daily_report_{today}.xlsx"}
    )


def format_date(date_str):
    """Format a date string to dd/mm/yyyy format."""
    if not date_str:
        return ""
    try:
        # Try ISO format first
        date_obj = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S.%f')
        return date_obj.strftime('%d/%m/%Y')
    except ValueError:
        try:
            # Try standard datetime format
            date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            return date_obj.strftime('%d/%m/%Y')
        except ValueError:
            return date_str  # Return original string if format is incorrect


def format_date(date_str):
    """Format a date string to dd/mm/yyyy format."""
    if not date_str:
        return ""
    try:
        # Try ISO format first
        date_obj = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S.%f')
        return date_obj.strftime('%d/%m/%Y')
    except ValueError:
        try:
            # Try standard datetime format
            date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            return date_obj.strftime('%d/%m/%Y')
        except ValueError:
            return date_str  # Return original string if format is incorrect



def format_date(date_str):
    """Format a date string to dd/mm/yyyy format."""
    if not date_str:
        return ""
    try:
        # Try ISO format first
        date_obj = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S.%f')
        return date_obj.strftime('%d/%m/%Y')
    except ValueError:
        try:
            # Try standard datetime format
            date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            return date_obj.strftime('%d/%m/%Y')
        except ValueError:
            return date_str  # Return original string if format is incorrect






@app.route('/upload_file/<int:task_id>', methods=['POST'])
@role_required('employee')
def upload_file(task_id):
    file = request.files['file']
    if file:
        file_path = os.path.join('./uploads', file.filename)
        file.save(file_path)
        tasks = load_json(TASK_FILE)
        for task in tasks:
            if task['id'] == task_id and task['assigned_to'] == session['user']:
                task['files'].append(file.filename)
                save_json(TASK_FILE, tasks)
                return jsonify({"message": "File uploaded successfully"}), 200
    return jsonify({"error": "File upload failed"}), 400


@app.route('/generate_report', methods=['GET'])
@role_required('admin')
def generate_report():
    tasks = load_json(TASK_FILE)
    report_path = os.path.join(DATA_FOLDER, 'task_report.csv')
    with open(report_path, 'w') as f:
        f.write("Name,Description,Created By,Assigned To,Creation Time,Assignment Time,Deadline,Stage\n")
        for task in tasks:
            f.write(f"{task['name']},{task['description']},{task['created_by']},{task['assigned_to']}," +
                    f"{task['creation_time']},{task['assignment_time']},{task['deadline']},{task['stage']}\n")
    return send_file(report_path, as_attachment=True)


if __name__ == '__main__':
    app.run(debug=True)
