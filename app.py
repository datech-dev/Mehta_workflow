from flask import Flask, request, jsonify, render_template, redirect, send_file, url_for, session, flash, Response

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
import csv




app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_COOKIE_SECURE'] = False  # Store sessions on the filesystem
Session(app)

# Configurations
DATA_FOLDER = './data'
USER_FILE = os.path.join(DATA_FOLDER, 'users.json')
TASK_FILE = os.path.join(DATA_FOLDER, 'tasks.json')
CUSTOMER_FILE=os.path.join(DATA_FOLDER, 'client.json')
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
            print(f"Loaded users data {file_path}: {data}")  # Debugging log
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
        return redirect(url_for('base'))
    return redirect(url_for('login'))


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
        return redirect(url_for('login'))
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
        return redirect(url_for('login'))  # Redirect to login if not logged in
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
    


@app.route('/view_task/<int:task_id>', methods=['GET', 'POST'])
def view_task(task_id):
    tasks = load_json(TASK_FILE)  # Load all tasks from JSON file
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

    if request.method == 'POST':
        # Extract form data
        new_status = request.form.get('status')
        new_comment = request.form.get('comment')
        new_invoice_status = request.form.get('invoice_status')

        # Fetch current logged-in user
        if 'user' not in session:
            flash("You must be logged in to make changes.", "danger")
            return redirect(url_for('login'))
        commented_by = session['user']  # Get the logged-in user from session

        # Ensure a comment is added when updating the stage
        if new_status and new_status != task['stage'] and not new_comment:
            flash("Comments are mandatory when changing the stage.", "danger")
            return redirect(url_for('view_task', task_id=task_id))

        # Record stage change with comment and commented by
        if new_status and new_status != task['stage']:
            change_entry = {
                'stage': new_status,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'comment': new_comment or "No comment provided",
                'commented_by': commented_by
            }
            task['stage_changes'].append(change_entry)
            task['stage'] = new_status  # Update the current stage

        # Add a comment without changing the stage
        elif new_comment:
            change_entry = {
                'stage': "-",
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'comment': new_comment,
                'commented_by': commented_by
            }
            task['stage_changes'].append(change_entry)

        # Handle invoice status updates with timestamp and commented_by
        if new_invoice_status:
            invoice_status_entry = {
                'invoice_status': new_invoice_status,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'commented_by': commented_by
            }
            task['invoice_status_history'].append(invoice_status_entry)

        # Save the updated task back to the JSON file
        save_json(TASK_FILE, tasks)
        flash("Task updated successfully!", "success")
        return redirect(url_for('view_task', task_id=task_id))

    # Determine the latest invoice status
    latest_invoice_status = (
        task['invoice_status_history'][-1]['invoice_status']
        if task['invoice_status_history']
        else "No status provided"
    )

    # Render the task details with history and latest invoice status
    return render_template(
        'view.html', task=task, latest_invoice_status=latest_invoice_status
    )



@app.route('/assign_task')
def assign_task():
    return render_template('assign_task.html')


from datetime import datetime, timedelta

import csv

@app.route('/create_task', methods=['GET', 'POST'])
@role_required('Admin')  # Ensure only admins can access this page
def create_task():
    try:
        if request.method == 'POST':
            data = request.form

            # Get the form fields (updated to match HTML names)
            task_name = data.get('taskName')
            task_description = data.get('description')
            task_deadline = data.get('deadline')
            assigned_to = data.get('assigned_to')
            client_name = data.get('clientname')  # Added client name field

            unique_task_id = f"{task_name}_{task_deadline}_{assigned_to}_{client_name}"  # Update unique ID

            # Check if the required fields are present
            if not task_name or not task_description or not task_deadline or not assigned_to or not client_name:
                flash("All fields are required!", "error")
                return redirect(url_for('create_task'))

            # Parse and validate the deadline
            try:
                parsed_deadline = datetime.strptime(task_deadline, '%Y-%m-%dT%H:%M')
                formatted_deadline = parsed_deadline.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                flash("Invalid deadline format!", "error")
                return redirect(url_for('create_task'))

            tasks = load_json(TASK_FILE)

            # Check if the task already exists
            for task in tasks:
                if task.get('unique_id') == unique_task_id:
                    flash("This task already exists.", "error")
                    return redirect(url_for('create_task'))

            # Find the assigned user
            user = get_user_by_username(assigned_to)
            if not user:
                flash("User not found!", "error")
                return redirect(url_for('create_task'))

            # Add the new task to the list
            new_task = {
                "id": len(tasks) + 1,
                "unique_id": unique_task_id,
                "name": task_name,
                "description": task_description,
                "created_by": session['user'],
                "assigned_to": assigned_to,
                "client_name": client_name,
                "deadline": formatted_deadline,
                "comments": [],
                "blocking_reasons": [],
                "files": [],
                "stage": "Allotted",
                "creation_time": datetime.utcnow().isoformat(),
            }
            print(new_task)
            tasks.append(new_task)
            save_json(TASK_FILE, tasks)

            # Notify the assigned user via email
            subject = f"New Task Assigned: {task_name}"
            message_body = f"Hello {user['username']},\n\n" \
                        f"You have been assigned a new task:\n" \
                        f"Task Name: {task_name}\n" \
                        f"Description: {task_description}\n" \
                        f"Client Name: {client_name}\n" \
                        f"Deadline: {formatted_deadline}\n\n" \
                        f"Best regards,\nTask Manager Team"
            send_email(subject, user['email'], message_body)

            flash("Task created and email sent successfully!")
            return redirect(url_for('dashboard'))

        # Load users and clients from the data sources
        users = load_users()

        # Load clients from CSV
        clients = []
        with open('clients.csv', mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            clients = [row for row in reader]

        return render_template('create_task.html', users=users, clients=clients)

    except Exception as e:
        print(f"Error: {e}")
        flash("An error occurred while creating the task.", "error")
        return redirect(url_for('create_task'))

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
        'Task ID', 'Task Name', 'Current Stage', 
        'Stage Change', 'Stage Timestamp', 'Stage Comment', 'Commented By'
    ]
    for col_num, header in enumerate(stage_changes_headers):
        stage_changes_sheet.write(0, col_num, header)

    # Write headers for invoice status sheet
    invoice_status_headers = [
        'Task ID', 'Task Name', 'Invoice Status', 'Invoice Status Timestamp', 'Invoice Status Commented By'
    ]
    for col_num, header in enumerate(invoice_status_headers):
        invoice_status_sheet.write(0, col_num, header)

    # Populate stage changes sheet
    stage_row = 1
    for task in tasks:
        task_id = task.get('id', '')
        task_name = task.get('name', '')
        current_stage = task.get('stage', '')

        stage_changes = task.get('stage_changes', []) or [{}]
        
        # Include tasks without stage changes
        for stage_change in stage_changes:
            stage_changes_sheet.write(stage_row, 0, task_id)
            stage_changes_sheet.write(stage_row, 1, task_name)
            stage_changes_sheet.write(stage_row, 2, current_stage)
            stage_changes_sheet.write(stage_row, 3, stage_change.get('stage', ''))
            stage_changes_sheet.write(stage_row, 4, stage_change.get('timestamp', ''))
            stage_changes_sheet.write(stage_row, 5, stage_change.get('comment', ''))
            stage_changes_sheet.write(stage_row, 6, stage_change.get('commented_by', ''))
            stage_row += 1

    # Populate invoice status updates sheet
    invoice_row = 1
    for task in tasks:
        task_id = task.get('id', '')
        task_name = task.get('name', '')

        invoice_status_history = task.get('invoice_status_history', [])

        for invoice_status in invoice_status_history:
            invoice_status_sheet.write(invoice_row, 0, task_id)
            invoice_status_sheet.write(invoice_row, 1, task_name)
            invoice_status_sheet.write(invoice_row, 2, invoice_status.get('invoice_status', ''))
            invoice_status_sheet.write(invoice_row, 3, invoice_status.get('timestamp', ''))
            invoice_status_sheet.write(invoice_row, 4, invoice_status.get('commented_by', ''))
            invoice_row += 1

    workbook.close()
    output.seek(0)

    # Send the Excel file as a response
    return Response(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment;filename=tasks_report.xlsx"}
    )

@app.route('/generate_report')
def generate_report():
    tasks = load_json(TASK_FILE)
    report_path = os.path.join(DATA_FOLDER, 'task_report.csv')
    with open(report_path, 'w') as f:
        f.write("Name,Description,Created By,Assigned To,Creation Time,Deadline,Stage\n")
        for task in tasks:
            f.write(f"{task['name']},{task['description']},{task['created_by']},{task['assigned_to']}," +
                    f"{task['creation_time']},{task['deadline']},{task['stage']}\n")
    return send_file(report_path, as_attachment=True)

@app.route('/add-client', methods=['POST'])
def add_client():
    client = request.json
    if not client:
        return jsonify({"error": "No client data provided"}), 400

    # Append the client data to the CSV file
    with open('clients.csv', mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([client['clientName'], client['Group'], client['Type'], client['year'], client['Work'], client['Demand'], client['Department']])
    
    return jsonify({"message": "Client added to CSV successfully"}), 200


# Route to fetch clients from CSV
@app.route('/get-clients', methods=['GET'])
def get_clients():
    clients = []
    try:
        with open('clients.csv', mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                
                
                clients.append(row)
                print(clients)
    except FileNotFoundError:
        return jsonify({"error": "CSV file not found"}), 404

    return jsonify(clients), 200


@app.route('/delete-client', methods=['POST'])
def delete_client():
    client_name = request.json.get('clientName')
    if not client_name:
        return jsonify({"error": "Client name not provided"}), 400

    try:
        clients = []
        with open('clients.csv', mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row['Client_Name'] != client_name:
                    clients.append(row)

        with open('clients.csv', mode='w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=clients[0].keys())
            writer.writeheader()
            writer.writerows(clients)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "Client deleted successfully"}), 200



@app.route('/client', endpoint='clients')
def client():
    # your logic here
    return render_template('client.html')


if __name__ == '__main__':
    app.run(debug=True)
