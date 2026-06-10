from app import app
from database import db
from models import Usuario

with app.app_context():
    db.create_all()