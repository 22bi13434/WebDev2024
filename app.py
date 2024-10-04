from flask import Flask, render_template, request, redirect, url_for, flash, session
from firebase_admin import credentials, firestore, initialize_app
import hashlib
import secrets
from datetime import timedelta
import google.generativeai as genai
from google.ai.generativelanguage_v1beta.types import content
import json

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

cred = credentials.Certificate('crd.json')
initialize_app(cred)
db = firestore.client()

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
            return render_template('register.html', message="Passwords do not match")
        
        salt = secrets.token_bytes(20) #20 ký tự ngẫu nhiên
        combined_pw = f"{salt}{password}"
        hashed_password = hashlib.sha256(combined_pw.encode('utf-8')).hexdigest()

        user = db.collection('users').document(email).get()
        if user.exists:
            flash('Email already registered')
            return render_template('register.html', message="Email already registered")
        
        db.collection('users').document(email).set({
            'name': name,
            'password': hashed_password,
            'salt': str(salt)
        })

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
        user_doc = db.collection('users').document(email).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            combined_pw = f"{user_data['salt']}{password_input}"
            
            if user_data['password'] == hashlib.sha256(combined_pw.encode('utf-8')).hexdigest():
                session['user'] = email
                return redirect(url_for('todo_list'))
        flash('Invalid email or password')
        return render_template("login.html", message="Login information is incorrect")
    
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
            return render_template('change_password.html', message="New passwords do not match")
        user_doc = db.collection('users').document(session['user']).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            combined_pw = f"{user_data['salt']}{current_password}"
            if user_data['password'] != hashlib.sha256(combined_pw.encode('utf-8')).hexdigest():
                flash('Current password is incorrect')
                return render_template('change_password.html', message="Current password is incorrect")
            new_combined_pw = f"{user_data['salt']}{new_password}"
            new_hashed_password = hashlib.sha256(new_combined_pw.encode('utf-8')).hexdigest()
            db.collection('users').document(session['user']).update({'password': new_hashed_password})
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

    user_ref = db.collection('users').document(session['user']).get()
    user_data = user_ref.to_dict()
    user_name = user_data.get('name', 'User').split()[-1]
    user_image = user_data.get('profile_image', url_for('static', filename='img/default-user.png'))

    todos = db.collection('todos').where('user_email', '==', session['user']).order_by('timestamp', direction=firestore.Query.DESCENDING).get()
    
    return render_template('todo_list.html', todos=[{'id': todo.id, **todo.to_dict()} for todo in todos], user_name=user_name, user_image=user_image)

@app.route('/add_todo', methods=['POST'])
def add_todo():
    if 'user' not in session:
        return redirect(url_for('login'))
    todo = request.form['todo']
    db.collection('todos').add({
        'name': todo,
        'status': 'pending',
        'timestamp': firestore.SERVER_TIMESTAMP,
        'user_email': session['user']
    })
    return redirect(url_for('todo_list'))

@app.route('/update_todo/<todo_id>', methods=['POST'])
def update_todo(todo_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    status = request.form['status']
    db.collection('todos').document(todo_id).update({'status': status})
    return redirect(url_for('todo_list'))

@app.route('/remove_todo', methods=['POST'])
def remove_todo():
    if 'user' not in session:
        return redirect(url_for('login'))
    todo_id = request.form.get('todo_id')
    if not todo_id:
        return 'Todo ID is required', 400
    try:
        db.collection('todos').document(todo_id).delete()
        return 'Success', 200
    except Exception as e:
        print(f"Error removing todo: {e}")
        return 'Error removing todo', 500

@app.route('/remove_all_todos', methods=['POST'])
def remove_all_todos():
    if 'user' not in session:
        return redirect(url_for('login'))
    try:
        todos_ref = db.collection('todos').where('user_email', '==', session['user'])
        docs = todos_ref.get()
        for doc in docs:
            doc.reference.delete()
        return 'Success', 200
    except Exception as e:
        print(f"Error removing all todos: {e}")
        return 'Error removing all todos', 500

@app.errorhandler(404)
def page_not_found(e):
    return redirect(url_for('login'))

@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    user_doc = db.collection('users').document(session['user']).get()
    if not user_doc.exists:
        flash('User not found')
        return redirect(url_for('todo_list'))

    user_data = user_doc.to_dict()

    if request.method == 'POST':
        name = request.form['name']
        profile_image = request.files.get('profile_image')  # File upload

        # Update name
        db.collection('users').document(session['user']).update({'name': name})

        # Check if an image is uploaded and save it to storage
        if profile_image and profile_image.filename != '':
            # Generate unique filename for profile image
            image_filename = f"{session['user']}_profile.jpg"
            profile_image_path = f"static/upload/{image_filename}"
            profile_image.save(profile_image_path)

            # Update Firestore with the new image URL
            db.collection('users').document(session['user']).update({'profile_image': url_for('static', filename=f'upload/{image_filename}')})

        flash('Profile updated successfully')
        return redirect(url_for('todo_list'))

    return render_template('edit_profile.html', user_data=user_data, email=session['user'])

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