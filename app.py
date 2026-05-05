from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_login import LoginManager, login_user, login_required, current_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from models import db, Admin, Opportunity

# ✅ static_url_path='' means admin.css and admin.js are served from root
app = Flask(__name__, template_folder='sky', static_folder='sky', static_url_path='')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = "your-secret-key-change-this"

CORS(app, supports_credentials=True)
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))

@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({"error": "Unauthorized. Please log in."}), 401

with app.app_context():
    db.create_all()

# ---------------- SERVE HTML PAGE ---------------- #
@app.route("/")
@app.route("/login")
@app.route("/admin")
def serve_admin():
    return render_template("admin.html")


# ================================================
#                AUTHENTICATION
# ================================================

@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.json
    if not data.get("full_name") or not data.get("email") or not data.get("password"):
        return jsonify({"error": "All fields are required"}), 400
    if len(data["password"]) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if data["password"] != data.get("confirm_password"):
        return jsonify({"error": "Passwords do not match"}), 400
    if Admin.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "An account with this email already exists"}), 400
    hashed_password = generate_password_hash(data["password"])
    user = Admin(full_name=data["full_name"], email=data["email"], password_hash=hashed_password)
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "Signup successful"})


@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    if not data.get("email") or not data.get("password"):
        return jsonify({"error": "Email and password are required"}), 400
    user = Admin.query.filter_by(email=data["email"]).first()
    if not user or not check_password_hash(user.password_hash, data["password"]):
        return jsonify({"error": "Invalid email or password"}), 401
    remember = data.get("remember_me", False)
    login_user(user, remember=remember)
    return jsonify({
        "message": "Login successful",
        "user": {"id": user.id, "full_name": user.full_name, "email": user.email}
    })


@app.route("/api/logout", methods=["GET", "POST"])
@login_required
def logout():
    logout_user()
    return jsonify({"message": "Logged out successfully"})


@app.route("/api/forgot-password", methods=["POST"])
def forgot_password():
    data = request.json
    email = data.get("email")
    if not email:
        return jsonify({"error": "Email is required"}), 400
    user = Admin.query.filter_by(email=email).first()
    if user:
        s = URLSafeTimedSerializer(app.secret_key)
        token = s.dumps(email, salt="password-reset")
        reset_link = f"http://localhost:5000/api/reset-password/{token}"
        print(f"\n{'='*60}\n[RESET LINK] {reset_link}\n{'='*60}\n")
    return jsonify({"message": "If that email is registered, a reset link has been sent."})


@app.route("/api/reset-password/<token>", methods=["POST"])
def reset_password(token):
    s = URLSafeTimedSerializer(app.secret_key)
    try:
        email = s.loads(token, salt="password-reset", max_age=3600)
    except SignatureExpired:
        return jsonify({"error": "Reset link has expired"}), 400
    except BadSignature:
        return jsonify({"error": "Invalid reset link"}), 400
    data = request.json
    new_password = data.get("password")
    if not new_password or len(new_password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    user = Admin.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    return jsonify({"message": "Password reset successful"})


# ================================================
#            OPPORTUNITY MANAGEMENT
# ================================================

VALID_CATEGORIES = ["Technology", "Business", "Design", "Marketing", "Data Science", "Other"]

@app.route("/api/opportunities", methods=["GET"])
@login_required
def get_opportunities():
    ops = Opportunity.query.filter_by(admin_id=current_user.id).all()
    return jsonify([op.to_dict() for op in ops])


@app.route("/api/opportunities/<int:id>", methods=["GET"])
@login_required
def get_opportunity(id):
    op = Opportunity.query.filter_by(id=id, admin_id=current_user.id).first()
    if not op:
        return jsonify({"error": "Not found"}), 404
    return jsonify(op.to_dict())


@app.route("/api/opportunities", methods=["POST"])
@login_required
def add_opportunity():
    data = request.json
    required_fields = ["name", "duration", "start_date", "description", "skills", "category", "future_opportunities"]
    for field in required_fields:
        if not data.get(field):
            return jsonify({"error": f"'{field}' is required"}), 400
    if data["category"] not in VALID_CATEGORIES:
        return jsonify({"error": "Invalid category"}), 400
    op = Opportunity(
        name=data["name"], duration=data["duration"], start_date=data["start_date"],
        description=data["description"], skills=data["skills"], category=data["category"],
        future_opportunities=data["future_opportunities"],
        max_applicants=data.get("max_applicants"),
        admin_id=current_user.id
    )
    db.session.add(op)
    db.session.commit()
    return jsonify({"message": "Opportunity created successfully", "opportunity": op.to_dict()}), 201


@app.route("/api/opportunities/<int:id>", methods=["PUT"])
@login_required
def update_opportunity(id):
    op = Opportunity.query.filter_by(id=id, admin_id=current_user.id).first()
    if not op:
        return jsonify({"error": "Not found or access denied"}), 403
    data = request.json
    allowed_fields = ["name", "duration", "start_date", "description", "skills", "category", "future_opportunities", "max_applicants"]
    for key in allowed_fields:
        if key in data:
            setattr(op, key, data[key])
    db.session.commit()
    return jsonify({"message": "Updated successfully", "opportunity": op.to_dict()})


@app.route("/api/opportunities/<int:id>", methods=["DELETE"])
@login_required
def delete_opportunity(id):
    op = Opportunity.query.filter_by(id=id, admin_id=current_user.id).first()
    if not op:
        return jsonify({"error": "Not found or access denied"}), 403
    db.session.delete(op)
    db.session.commit()
    return jsonify({"message": "Deleted successfully"})


if __name__ == "__main__":
    app.run(debug=True)