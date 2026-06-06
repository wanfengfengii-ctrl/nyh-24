from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class IceHouse(db.Model):
    __tablename__ = 'ice_houses'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    build_year = db.Column(db.Integer)
    capacity = db.Column(db.Integer, nullable=False)
    is_open = db.Column(db.Boolean, default=False)
    high_risk = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    batches = db.relationship('IceBatch', backref='ice_house', lazy=True, cascade='all, delete-orphan')
    inspections = db.relationship('Inspection', backref='ice_house', lazy=True, cascade='all, delete-orphan')
    melt_losses = db.relationship('MeltLoss', backref='ice_house', lazy=True, cascade='all, delete-orphan')
    repairs = db.relationship('Repair', backref='ice_house', lazy=True, cascade='all, delete-orphan')

    def has_unfinished_repairs(self):
        return any(r.status != 'completed' for r in self.repairs)

    def update_risk_status(self):
        has_seepage = any(i.seepage for i in self.inspections)
        has_severe_melt = any(i.melt_level == 'severe' for i in self.inspections)
        self.high_risk = has_seepage or has_severe_melt


class IceBatch(db.Model):
    __tablename__ = 'ice_batches'
    id = db.Column(db.Integer, primary_key=True)
    ice_house_id = db.Column(db.Integer, db.ForeignKey('ice_houses.id'), nullable=False)
    entry_date = db.Column(db.Date, nullable=False)
    ice_count = db.Column(db.Integer, nullable=False)
    expected_storage_period = db.Column(db.Integer, nullable=False)
    current_remaining = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Inspection(db.Model):
    __tablename__ = 'inspections'
    id = db.Column(db.Integer, primary_key=True)
    ice_house_id = db.Column(db.Integer, db.ForeignKey('ice_houses.id'), nullable=False)
    inspection_date = db.Column(db.Date, nullable=False)
    temperature = db.Column(db.Float, nullable=False)
    humidity = db.Column(db.Float, nullable=False)
    seepage = db.Column(db.Boolean, default=False)
    melt_level = db.Column(db.String(20), default='normal')
    suggestions = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MeltLoss(db.Model):
    __tablename__ = 'melt_losses'
    id = db.Column(db.Integer, primary_key=True)
    ice_house_id = db.Column(db.Integer, db.ForeignKey('ice_houses.id'), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey('ice_batches.id'), nullable=False)
    record_date = db.Column(db.Date, nullable=False)
    loss_amount = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    batch = db.relationship('IceBatch', backref='melt_losses')


class Repair(db.Model):
    __tablename__ = 'repairs'
    id = db.Column(db.Integer, primary_key=True)
    ice_house_id = db.Column(db.Integer, db.ForeignKey('ice_houses.id'), nullable=False)
    report_date = db.Column(db.Date, nullable=False)
    issue_description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')
    repair_date = db.Column(db.Date)
    repair_cost = db.Column(db.Float, default=0)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
