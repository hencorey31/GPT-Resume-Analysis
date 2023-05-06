import openai
from flask import Flask, request, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
db = SQLAlchemy(app)
auth = HTTPBasicAuth()

openai.api_key = "Your API key here"

# Database models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def hash_password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

class Resume(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class JobPosting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

with app.app_context():
    db.create_all()

# Authentication
@auth.verify_password
def verify_password(username, password):
    user = User.query.filter_by(username=username).first()
    if user and user.verify_password(password):
        return user

# API Endpoints
@app.route('/api/register', methods=['POST'])
def register():
    try:
        username = request.form['username']
        password = request.form['password']
        if username is None or password is None:
            return jsonify({'error': 'Username and password are required'}), 400
        if User.query.filter_by(username=username).first() is not None:
            return jsonify({'error': 'User already exists'}), 400
        user = User(username=username)
        user.hash_password(password)
        db.session.add(user)
        db.session.commit()
        return jsonify({'username': user.username}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload_resume', methods=['POST'])
@auth.login_required
def upload_resume():
    resume_data = request.form['resume_data']
    user_id = auth.current_user().id
    resume = Resume(data=resume_data, user_id=user_id)
    db.session.add(resume)
    db.session.commit()
    return jsonify({"resume_id": resume.id}), 201

@app.route('/api/upload_job_posting', methods=['POST'])
@auth.login_required
def upload_job_posting():
    job_posting_data = request.form['job_posting_data']
    user_id = auth.current_user().id
    job_posting = JobPosting(data=job_posting_data, user_id=user_id)
    db.session.add(job_posting)
    db.session.commit()
    return jsonify({"job_posting_id": job_posting.id}), 201

@app.route('/api/analyze_resume/<int:resume_id>/<int:job_posting_id>', methods=['GET'])
@auth.login_required
def analyze_resume(resume_id, job_posting_id):
    resume = Resume.query.get(resume_id)
    job_posting = JobPosting.query.get(job_posting_id)
    if resume and job_posting:
        try:
            analysis_result = analyze_resume_gpt3(resume.data, job_posting.data)
            return jsonify({"analysis_result": analysis_result}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "Invalid resume_id or job_posting_id"}), 404
    
@app.route('/api/analyze_multiple_resumes/<string:resume_ids>/<int:job_posting_id>', methods=['GET'])
@auth.login_required
def analyze_multiple_resumes(resume_ids, job_posting_id):
    user_id = auth.current_user().id
    resume_ids = [int(x) for x in resume_ids.split(',')]

    resumes = Resume.query.filter(Resume.id.in_(resume_ids), Resume.user_id == user_id).all()
    job_posting = JobPosting.query.filter_by(id=job_posting_id, user_id=user_id).first()

    if not resumes or not job_posting:
        return jsonify({"error": "Invalid resume IDs or job posting ID"}), 400

    resume_contents = [resume.data for resume in resumes]
    job_description = job_posting.data

    analyzed_resumes = []
    for resume_content in resume_contents:
        prompt = f"In terms of fitness to the job description \"{job_description}\", rank the applicants from first to last (for example, 1. 2. 3.) by applicant name and resume ID based on their resume: \"{resume_content}\".After each ranking, justify your decision. Make the justifications short and consice."

        response = openai.Completion.create(
            engine="text-davinci-002",
            prompt=prompt,
            temperature=0.5,
            max_tokens=150,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0
        )

        analysis = response.choices[0].text.strip()
        analyzed_resumes.append({
            "resume_content": resume_content,
            "analysis": analysis
        })

    return jsonify({"analyzed_resumes": analyzed_resumes}), 200

    
def analyze_resume_gpt3(resume_text, job_description):
    prompt = f"On a scale of 1-10, how well does this resume \"{resume_text}\" fit the given job description: \"{job_description}\"? Give a moderate description as to why."

    response = openai.Completion.create(
        engine="text-davinci-002",
        prompt=prompt,
        max_tokens=150,
        n=1,
        stop=None,
        temperature=0.5,
    )

    return response.choices[0].text.strip()

if __name__ == '__main__':
    app.run(debug=True)
