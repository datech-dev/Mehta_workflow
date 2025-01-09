from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash, Response

import os
import json
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_session import Session
import xlsxwriter
import io

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_COOKIE_SECURE'] = False  # Store sessions on the filesystem
Session(app)

# Configurations
DATA_FOLDER = './data'
USER_FILE = os.path.join(DATA_FOLDER, 'users.json')
TASK_FILE = os.path.join(DATA_FOLDER, 'tasks.json')


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
        
        # Create a new user with a hashed password
        new_user = {
            "username": data['username'],
            "password": generate_password_hash(data['password']),  # Hash the password
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
    print(session)
    print("Role:", role)
    tasks = load_json(TASK_FILE) 
     # Load the task data from the JSON file

    # Filter tasks based on the role
    if role == 'Admin':
        user_tasks = tasks  # Admins see all tasks
    elif role == 'Employee':
        user_tasks = [task for task in tasks if task['assigned_to'] == username]
        print(username)  # Employees see only assigned tasks
    else:
        user_tasks = []

    return jsonify(user_tasks)


@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    role = session.get('role')
    return render_template('dashboard.html', role=role)


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

        # Check if the required fields are present
        if not task_name or not task_description or not task_deadline or not assigned_to:
            flash("All fields are required!", "error")
            return redirect(url_for('create_task'))
        
        tasks = load_json(TASK_FILE)

        # Find the assigned user by their username
        user = get_user_by_username(assigned_to)  # Assuming this is a function that fetches the user by their username
        if not user:
            flash("User not found!", "error")
            return redirect(url_for('create_task'))

        new_task = {
            "id": len(tasks) + 1,
            "name": task_name,
            "description": task_description,
            "created_by": session['user'],
            "assigned_to": assigned_to,  # The username of the assignee
            "assigned_to_name": user['username'],  # Store the user's name for easier reference
            "stage": "Creation",
            "creation_time": datetime.utcnow().isoformat(),
            "assignment_time": None,
            "deadline": task_deadline,
            "comments": [],
            "blocking_reasons": [],
            "files": []
        }

        tasks.append(new_task)
        save_json(TASK_FILE, tasks)
        flash("Task created successfully!")
        return redirect(url_for('dashboard'))

    # Load the list of users from your data source
    users = load_users()  # Get the users from the JSON file
    return render_template('create_task.html', users=users)



@app.route('/assign_task/<int:task_id>', methods=['POST'])
@role_required('admin')
def assign_task(task_id):
    data = request.json
    tasks = load_json(TASK_FILE)
    for task in tasks:
        if task['id'] == task_id:
            task['assigned_to'] = data['assigned_to']
            task['assignment_time'] = datetime.utcnow().isoformat()
            task['stage'] = "Assigned"
            save_json(TASK_FILE, tasks)
            # Add email notification logic here
            return jsonify({"message": "Task assigned successfully"}), 200
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
        'view_task.html', task=task, latest_invoice_status=latest_invoice_status
    )









import pandas as pd
from flask import send_file


@app.route('/export_tasks', methods=['GET'])
def export_tasks():
    tasks = load_json(TASK_FILE)
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet()

    # Write headers
    headers = [
        'Task ID', 'Task Name', 'Current Stage', 
        'Stage Change', 'Stage Timestamp', 'Stage Comment', 'Commented By', 
        'Invoice Status', 'Invoice Status Timestamp', 'Invoice Status Commented By'
    ]
    for col_num, header in enumerate(headers):
        worksheet.write(0, col_num, header)

    # Populate rows
    row = 1
    for task in tasks:
        task_id = task.get('id', '')
        task_name = task.get('name', '')
        current_stage = task.get('stage', '')

        # Handle stage changes and invoice statuses
        invoice_status_history = task.get('invoice_status_history', [])
        stage_changes = task.get('stage_changes', [])
        
        # Iterate through stage changes
        for stage_change in stage_changes:
            worksheet.write(row, 0, task_id)
            worksheet.write(row, 1, task_name)
            worksheet.write(row, 2, current_stage)
            worksheet.write(row, 3, stage_change.get('stage', ''))
            worksheet.write(row, 4, stage_change.get('timestamp', ''))
            worksheet.write(row, 5, stage_change.get('comment', ''))
            worksheet.write(row, 6, stage_change.get('commented_by', ''))

            # For each stage change, get the corresponding invoice status history
            for invoice_status in invoice_status_history:
                worksheet.write(row, 7, invoice_status.get('invoice_status', ''))
                worksheet.write(row, 8, invoice_status.get('timestamp', ''))
                worksheet.write(row, 9, invoice_status.get('commented_by', ''))

            row += 1

    workbook.close()
    output.seek(0)

    # Send the Excel file as a response
    return Response(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment;filename=tasks_report.xlsx"}
    )






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
