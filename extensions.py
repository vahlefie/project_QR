from flask_sqlalchemy import SQLAlchemy

# Objek ekstensi database dipisahkan agar model bisa keluar dari app.py tanpa circular import.
db = SQLAlchemy()
