from flask import Flask, render_template, request, redirect, url_for, flash, session
import hashlib
import secrets
from datetime import timedelta
import sqlite3
import os
import google.generativeai as genai
from google.ai.generativelanguage_v1beta.types import content
import json

UPLOAD_FOLDER = 'static/upload'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

genai.configure(api_key="AIzaSyAJluWpK03fnL4LOSk4RyRv4pHsDH96S9Q") 

generation_config = {
  "temperature": 1,
  "top_p": 0.95,
  "top_k": 64,
  "max_output_tokens": 8192,
  "response_schema": content.Schema(
    type = content.Type.OBJECT,
    properties = {
      "response": content.Schema(
        type = content.Type.ARRAY,
        items = content.Schema(
          type = content.Type.STRING,
        ),
      ),
    },
  ),
  "response_mime_type": "application/json",
}

model = genai.GenerativeModel(
  model_name="gemini-1.5-pro",
  generation_config=generation_config,
)
app = Flask(__name__)
app.secret_key = "abcabcabc"
app.permanent_session_lifetime = timedelta(days=10)

DATABASE = 'todolist_database.db'

if not os.path.exists(DATABASE):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 email TEXT PRIMARY KEY,
                 name TEXT,
                 password TEXT,
                 salt TEXT,
                 profile_image TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS todos (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 name TEXT,
                 status TEXT,
                 user_email TEXT,
                 timestamp TEXT,
                 FOREIGN KEY(user_email) REFERENCES users(email))''')
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('todo_list'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user' in session:
        return redirect(url_for('todo_list'))
    
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password'].encode('utf-8')
        confirm_password = request.form['confirm_password'].encode('utf-8')

        if password != confirm_password:
            flash('Passwords do not match')
            return redirect(url_for('register'))
        
        salt = secrets.token_bytes(20)
        combined_pw = f"{salt}{password}"
        hashed_password = hashlib.sha256(combined_pw.encode('utf-8')).hexdigest()

        conn = get_db_connection()
        c = conn.cursor()

        c.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = c.fetchone()
        if user:
            flash('Email already registered')
            conn.close()
            return render_template('register.html')

        c.execute('INSERT INTO users (email, name, password, salt) VALUES (?, ?, ?, ?)',
                  (email, name, hashed_password, salt))
        conn.commit()
        conn.close()

        flash('Registration successful. Please login.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('todo_list'))
    
    if request.method == 'POST':
        email = request.form['email']
        password_input = request.form['password'].encode('utf-8')

        conn = get_db_connection()
        c = conn.cursor()

        c.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = c.fetchone()
        conn.close()

        if user:
            combined_pw = f"{user['salt']}{password_input}"
            if user['password'] == hashlib.sha256(combined_pw.encode('utf-8')).hexdigest():
                session['user'] = email
                return redirect(url_for('todo_list'))

        flash('Invalid email or password')
        return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        current_password = request.form['current_password'].encode('utf-8')
        new_password = request.form['new_password'].encode('utf-8')
        confirm_new_password = request.form['confirm_new_password'].encode('utf-8')

        if new_password != confirm_new_password:
            flash('New passwords do not match')
            return redirect(url_for('change_password'))
        if len(new_password) < 8:
            flash('Password must be at least 8 characters long.')
            return redirect(url_for('change_password'))

        conn = get_db_connection()
        c = conn.cursor()

        c.execute('SELECT * FROM users WHERE email = ?', (session['user'],))
        user = c.fetchone()

        combined_pw = f"{user['salt']}{current_password}"
        if user['password'] != hashlib.sha256(combined_pw.encode('utf-8')).hexdigest():
            conn.close()
            flash('Current password is incorrect')
            return redirect(url_for('change_password'))

        new_combined_pw = f"{user['salt']}{new_password}"
        new_hashed_password = hashlib.sha256(new_combined_pw.encode('utf-8')).hexdigest()
        c.execute('UPDATE users SET password = ? WHERE email = ?', (new_hashed_password, session['user']))
        conn.commit()
        conn.close()

        flash('Password changed successfully')
        return redirect(url_for('todo_list'))

    return render_template('change_password.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/todo_list')
def todo_list():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute('SELECT * FROM users WHERE email = ?', (session['user'],))
    user_data = c.fetchone()

    if not user_data:
        flash('User not found')
        return redirect(url_for('login'))

    user_name = user_data['name'].split()[-1]
    user_image = user_data['profile_image'] if 'profile_image' in user_data.keys() and user_data['profile_image'] else url_for('static', filename='img/default-user.png')

    c.execute('SELECT * FROM todos WHERE user_email = ? ORDER BY timestamp DESC', (session['user'],))
    todos = c.fetchall()
    
    conn.close()

    todos_list = [{'id': todo['id'], 'name': todo['name'], 'status': todo['status'], 'timestamp': todo['timestamp']} for todo in todos]

    return render_template('todo_list.html', todos=todos_list, user_name=user_name, user_image=user_image)

@app.route('/add_todo', methods=['POST'])
def add_todo():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    todo = request.form['todo']

    conn = get_db_connection()
    c = conn.cursor()

    c.execute('INSERT INTO todos (name, status, user_email, timestamp) VALUES (?, ?, ?, datetime("now"))',
              (todo, 'pending', session['user']))
    conn.commit()
    conn.close()

    return redirect(url_for('todo_list'))

@app.route('/update_todo/<todo_id>', methods=['POST'])
def update_todo(todo_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    status = request.form['status']

    conn = get_db_connection()
    c = conn.cursor()

    c.execute('UPDATE todos SET status = ? WHERE id = ?', (status, todo_id))
    conn.commit()
    conn.close()

    return redirect(url_for('todo_list'))

@app.route('/remove_todo', methods=['POST'])
def remove_todo():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    todo_id = request.form.get('todo_id')
    if not todo_id:
        return 'Todo ID is required', 400

    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('DELETE FROM todos WHERE id = ?', (todo_id,))
        conn.commit()
        conn.close()
        return 'Success', 200
    except Exception as e:
        print(f"Error removing todo: {e}")
        return 'Error removing todo', 500

UPLOAD_FOLDER = 'static/upload'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/remove_all_todos', methods=['POST'])
def remove_all_todos():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute('DELETE FROM todos WHERE user_email = ?', (session['user'],))
        conn.commit()
        conn.close()
        
        return 'Success', 200
    except Exception as e:
        print(f"Error removing all todos: {e}")
        return 'Error removing all todos', 500

@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('SELECT * FROM users WHERE email = ?', (session['user'],))
    user_data = c.fetchone()
    conn.close()

    if not user_data:
        flash('User not found')
        return redirect(url_for('todo_list'))

    if request.method == 'POST':
        name = request.form['name']
        profile_image = request.files.get('profile_image')

        conn = get_db_connection()
        c = conn.cursor()

        c.execute('UPDATE users SET name = ? WHERE email = ?', (name, session['user']))

        if profile_image and allowed_file(profile_image.filename):
            filename = f"{session['user']}_profile.jpg"
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            profile_image.save(image_path)

            c.execute('UPDATE users SET profile_image = ? WHERE email = ?',
                      (url_for('static', filename=f'upload/{filename}'), session['user']))

        conn.commit()
        conn.close()

        flash('Profile updated successfully')
        return redirect(url_for('todo_list'))

    return render_template('edit_profile.html', user_data=user_data, email=session['user'])

@app.errorhandler(404)
def page_not_found(e):
    return redirect(url_for('login'))

@app.route('/ask_ai', methods=['POST'])
def ask_ai():
    prompt = request.form['prompt']
    chat_session = model.start_chat(
    history=[
    {
        "role": "user",
        "parts": [
        "response the list of short todos: i want to make a flan cake",
        ],
    },
    {
        "role": "model",
        "parts": [
        "```json\n{\"response\": [\"Buy ingredients\", \"Preheat oven\", \"Make caramel\", \"Pour caramel in dish\", \"Blend egg mixture\", \"Pour mixture over caramel\", \"Bake in bain-marie\", \"Cool before inverting\"]}\n\n```",
        ],
    },
    ]
    )
    response = chat_session.send_message("response the list of short todos: " + prompt)
    response_dict = json.loads(response.text)
    suggestions = response_dict["response"]
    return {'suggestions': suggestions}

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5500)
