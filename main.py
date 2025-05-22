from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from psycopg import sql
import psycopg
import os
import json
import subprocess

app = Flask(__name__)
app.secret_key = 'a12f9c2b4d5e6f7g8h9i0jklmnopqrst'  # Needed for flashing messages

# --- Multimedia serving ---
@app.route('/multimedia/<path:filename>')
def serve_multimedia(filename):
    return send_from_directory('multimedia', filename)

# --- File handling settings ---
from werkzeug.utils import secure_filename
UPLOAD_TEXT_FOLDER = './multimedia/text'
UPLOAD_IMAGE_FOLDER = './multimedia/images'
ALLOWED_TEXT_EXTENSIONS = {'txt', 'csv'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_TEXT_FOLDER'] = UPLOAD_TEXT_FOLDER
app.config['UPLOAD_IMAGE_FOLDER'] = UPLOAD_IMAGE_FOLDER

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

# --- Delete file endpoint ---
@app.route('/delete-file', methods=['POST'])
def delete_file():
    if 'admin_id' not in session:
        flash('Login required.', 'danger')
        return redirect(url_for('login'))

    rel_path = request.form.get('file_path')
    full_path = os.path.join('multimedia', rel_path)

    try:
        os.remove(full_path)
        flash(f"Deleted {rel_path}", 'success')
    except FileNotFoundError:
        flash(f"File not found: {rel_path}", 'warning')
    except Exception as e:
        flash(f"Error deleting {rel_path}: {e}", 'danger')

    return redirect(url_for('upload_tool'))

# --- Replace file endpoint ---
@app.route('/replace-file', methods=['POST'])
def replace_file():
    if 'admin_id' not in session:
        flash('Login required.', 'danger')
        return redirect(url_for('login'))

    orig_path = request.form.get('orig_path')
    new_file = request.files.get('new_file')

    if not new_file or new_file.filename == '':
        flash('No replacement file selected.', 'warning')
        return redirect(url_for('upload_tool'))

    full_orig = os.path.join('multimedia', orig_path)
    try:
        new_file.save(full_orig)
        flash(f"Replaced {orig_path}", 'success')
    except Exception as e:
        flash(f"Error replacing {orig_path}: {e}", 'danger')

    return redirect(url_for('upload_tool'))

# --- Database connection settings ---
DB_NAME = 'house_of_emigrants'
DB_USER = 'postgres'
DB_PASS = '666'
DB_HOST = 'localhost'
DB_PORT = '5432'

def get_db_connection():
    return psycopg.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT
    )

# --- Routes ---
@app.route('/')
def homepage():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        conn = get_db_connection()
        cur = conn.cursor()

        query = sql.SQL("SELECT id_admin, email, password FROM admins WHERE email = %s")
        cur.execute(query, (email,))
        admin = cur.fetchone()
        cur.close()
        conn.close()

        if admin and admin[2] == password:
            session['admin_id'] = admin[0]
            session['admin_email'] = admin[1]
            flash('Login successful!', 'success')
            return redirect(url_for('homepage'))
        else:
            flash('Invalid credentials.', 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('homepage'))

@app.route('/changePassword')
def change_password():
    return render_template('changePassword.html')

@app.route('/dataExploration')
def data_exploration():
    conn = get_db_connection()
    cur = conn.cursor()

    # 1) Timeline: viajes por año (usando la función almacenada)
    cur.execute("SELECT * FROM get_yearly_travels();")
    timeline = cur.fetchall()

    # 1b) Drilldown: viajes por mes para cada año (usando la función almacenada)
    cur.execute("SELECT * FROM get_monthly_travels();")
    monthly = cur.fetchall()

    # Construcción del JSON para drilldown
    from collections import defaultdict
    drilldown_data = defaultdict(list)
    for year, month, _, count in monthly:
        drilldown_data[int(year)].append({"name": month, "y": count})
    drilldown_data = dict(drilldown_data)

    # 2) Top keywords (usando la función almacenada)
    cur.execute("SELECT * FROM get_top_keywords(%s);", (10,))
    word_freq = cur.fetchall()

    # 3) Geo distribution por ciudad (usando la función almacenada)
    cur.execute("SELECT * FROM get_city_distribution();")
    geo = cur.fetchall()

    # 4) Recent stories with full details (usando la función almacenada)
    cur.execute("SELECT * FROM get_story_details();")
    recent = cur.fetchall()

    cur.close()
    conn.close()

    # unpack the three chart datasets
    timeline_years, timeline_counts = zip(*timeline) if timeline else ([], [])
    wf_words, wf_counts             = zip(*word_freq) if word_freq else ([], [])
    geo_countries, geo_counts       = zip(*geo)      if geo       else ([], [])

    # build a list of dicts for rendering
    stories = []
    for row in recent:
        stories.append({
            'title':              row[0],
            'summary':            row[1],
            'main_first':         row[2],
            'main_last':          row[3],
            'sex':                row[4],
            'marital_status':     row[5],
            'education_level':    row[6],
            'legal_status':       row[7],
            'mentions':           row[8] or [],
            'departure_date':     row[9],
            'destination_city':   row[10],
            'destination_country':row[11],
            'motive':             row[12],
            'travel_duration':    row[13],
            'return_plans':       row[14],
            'methods':            row[15] or []
        })

    return render_template('dataExploration.html',
        timeline_years   = json.dumps([row[0] for row in timeline]),
        timeline_counts  = json.dumps([row[1] for row in timeline]),
        drilldown_data   = json.dumps(drilldown_data),
        wf_words         = json.dumps(list(wf_words)),
        wf_counts        = json.dumps(list(wf_counts)),
        geo_countries    = json.dumps(list(geo_countries)),
        geo_counts       = json.dumps(list(geo_counts)),
        stories          = stories
    )

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/uploadTool')
def upload_tool():
    if 'admin_id' not in session:
        flash('Please log in to access the upload tool.', 'warning')
        return redirect(url_for('login'))

    files = []
    for fname in os.listdir(app.config['UPLOAD_TEXT_FOLDER']):
        files.append({'name': fname, 'type': 'text', 'path': f'text/{fname}'})
    for fname in os.listdir(app.config['UPLOAD_IMAGE_FOLDER']):
        files.append({'name': fname, 'type': 'image', 'path': f'images/{fname}'})
    return render_template('uploadTool.html', files=files)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'admin_id' not in session:
        flash('Login required to upload.', 'danger')
        return redirect(url_for('login'))

    uploaded_files = request.files.getlist('files')
    upload_type    = request.form.get('type')

    if not uploaded_files:
        flash('No file selected!', 'warning')
        return redirect(url_for('upload_tool'))

    for file in uploaded_files:
        filename = secure_filename(file.filename)

        if file and upload_type == 'text' and allowed_file(filename, ALLOWED_TEXT_EXTENSIONS):
            save_path = os.path.join(app.config['UPLOAD_TEXT_FOLDER'], filename)
            file.save(save_path)
            try:
                subprocess.run(['python', 'dataExtraction.py', save_path], check=True)
                flash(f"Uploaded and processed text file: {filename}", "success")
            except subprocess.CalledProcessError as e:
                flash(f"Uploaded {filename}, but processing failed: {e}", "warning")

        elif file and upload_type == 'image' and allowed_file(filename, ALLOWED_IMAGE_EXTENSIONS):
            save_path = os.path.join(app.config['UPLOAD_IMAGE_FOLDER'], filename)
            file.save(save_path)
            flash(f"Uploaded image file: {filename}", "success")

        else:
            flash(f"File '{filename}' not allowed or wrong type.", "danger")

    return redirect(url_for('upload_tool'))

if __name__ == '__main__':
    app.run(debug=True)