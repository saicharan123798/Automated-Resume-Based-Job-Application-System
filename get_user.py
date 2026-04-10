from app import app
from models import db, User

with app.app_context():
    user = User.query.first()
    if user:
        print(f"Username: {user.username}")
    else:
        print("No users found.")
