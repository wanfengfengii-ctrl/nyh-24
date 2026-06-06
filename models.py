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

    def has_pending_rectifications(self):
        return any(t.status in ['pending', 'in_progress'] for t in self.rectification_tasks)

    def has_unreviewed_tasks(self):
        return any(t.status == 'completed' and not any(r.result == 'pass' for r in t.reviews) for t in self.rectification_tasks)

    def has_pending_approvals(self):
        return any(a.status == 'pending' for a in self.approval_requests)

    def can_be_opened(self):
        if self.has_unfinished_repairs():
            return False, '存在未完成的修缮工单'
        if self.has_pending_rectifications():
            return False, '存在未完成的整改任务'
        if self.high_risk:
            return False, '冰窖当前为高风险状态'
        return True, ''

    def update_risk_status(self):
        has_seepage = any(i.seepage for i in self.inspections)
        has_severe_melt = any(i.melt_level == 'severe' for i in self.inspections)
        self.high_risk = has_seepage or has_severe_melt
        return has_seepage, has_severe_melt


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


class RiskAlert(db.Model):
    __tablename__ = 'risk_alerts'
    id = db.Column(db.Integer, primary_key=True)
    ice_house_id = db.Column(db.Integer, db.ForeignKey('ice_houses.id'), nullable=False)
    alert_type = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), default='medium')
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    source_type = db.Column(db.String(50))
    source_id = db.Column(db.Integer)
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)

    ice_house = db.relationship('IceHouse', backref='risk_alerts')


class RectificationTask(db.Model):
    __tablename__ = 'rectification_tasks'
    id = db.Column(db.Integer, primary_key=True)
    ice_house_id = db.Column(db.Integer, db.ForeignKey('ice_houses.id'), nullable=False)
    risk_alert_id = db.Column(db.Integer, db.ForeignKey('risk_alerts.id'))
    task_no = db.Column(db.String(50), unique=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    requirement = db.Column(db.Text)
    deadline = db.Column(db.Date)
    status = db.Column(db.String(20), default='pending')
    assigned_to = db.Column(db.String(100))
    actual_finish_date = db.Column(db.Date)
    rectification_result = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    ice_house = db.relationship('IceHouse', backref='rectification_tasks')
    risk_alert = db.relationship('RiskAlert', backref='rectification_tasks')
    reviews = db.relationship('ReviewRecord', backref='rectification_task', lazy=True, cascade='all, delete-orphan')


class ReviewRecord(db.Model):
    __tablename__ = 'review_records'
    id = db.Column(db.Integer, primary_key=True)
    rectification_task_id = db.Column(db.Integer, db.ForeignKey('rectification_tasks.id'), nullable=False)
    review_date = db.Column(db.Date, nullable=False)
    reviewer = db.Column(db.String(100))
    result = db.Column(db.String(20), nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ApprovalRequest(db.Model):
    __tablename__ = 'approval_requests'
    id = db.Column(db.Integer, primary_key=True)
    ice_house_id = db.Column(db.Integer, db.ForeignKey('ice_houses.id'), nullable=False)
    request_type = db.Column(db.String(50), default='open')
    title = db.Column(db.String(200), nullable=False)
    reason = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')
    applicant = db.Column(db.String(100))
    apply_date = db.Column(db.Date, nullable=False)
    approver = db.Column(db.String(100))
    approval_date = db.Column(db.Date)
    approval_comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ice_house = db.relationship('IceHouse', backref='approval_requests')


class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text)
    related_type = db.Column(db.String(50))
    related_id = db.Column(db.Integer)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='notifications')


class TransferOrder(db.Model):
    __tablename__ = 'transfer_orders'
    id = db.Column(db.Integer, primary_key=True)
    transfer_no = db.Column(db.String(50), unique=True, nullable=False)
    from_house_id = db.Column(db.Integer, db.ForeignKey('ice_houses.id'), nullable=False)
    to_house_id = db.Column(db.Integer, db.ForeignKey('ice_houses.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    reason = db.Column(db.Text)
    applicant = db.Column(db.String(100))
    apply_date = db.Column(db.Date, nullable=False)
    approver = db.Column(db.String(100))
    approval_date = db.Column(db.Date)
    approval_comment = db.Column(db.Text)
    executor = db.Column(db.String(100))
    execute_date = db.Column(db.Date)
    receiver = db.Column(db.String(100))
    receive_date = db.Column(db.Date)
    receive_remark = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    from_house = db.relationship('IceHouse', foreign_keys=[from_house_id], backref='outgoing_transfers')
    to_house = db.relationship('IceHouse', foreign_keys=[to_house_id], backref='incoming_transfers')
    items = db.relationship('TransferItem', backref='transfer_order', lazy=True, cascade='all, delete-orphan')

    def total_quantity(self):
        return sum(item.quantity for item in self.items)

    def total_received(self):
        return sum(item.received_quantity or 0 for item in self.items)


class TransferItem(db.Model):
    __tablename__ = 'transfer_items'
    id = db.Column(db.Integer, primary_key=True)
    transfer_order_id = db.Column(db.Integer, db.ForeignKey('transfer_orders.id'), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey('ice_batches.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    received_quantity = db.Column(db.Integer, default=0)
    remark = db.Column(db.String(200))

    batch = db.relationship('IceBatch', backref='transfer_items')


class OutboundRecord(db.Model):
    __tablename__ = 'outbound_records'
    id = db.Column(db.Integer, primary_key=True)
    outbound_no = db.Column(db.String(50), unique=True, nullable=False)
    ice_house_id = db.Column(db.Integer, db.ForeignKey('ice_houses.id'), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey('ice_batches.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    purpose = db.Column(db.String(100), nullable=False)
    destination = db.Column(db.String(200))
    handler = db.Column(db.String(100))
    outbound_date = db.Column(db.Date, nullable=False)
    remark = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ice_house = db.relationship('IceHouse', backref='outbound_records')
    batch = db.relationship('IceBatch', backref='outbound_records')


class InventoryFlow(db.Model):
    __tablename__ = 'inventory_flows'
    id = db.Column(db.Integer, primary_key=True)
    ice_house_id = db.Column(db.Integer, db.ForeignKey('ice_houses.id'), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey('ice_batches.id'), nullable=False)
    flow_type = db.Column(db.String(30), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    balance_after = db.Column(db.Integer, nullable=False)
    related_type = db.Column(db.String(50))
    related_id = db.Column(db.Integer)
    operator = db.Column(db.String(100))
    operation_time = db.Column(db.DateTime, default=datetime.utcnow)
    remark = db.Column(db.String(200))

    ice_house = db.relationship('IceHouse', backref='inventory_flows')
    batch = db.relationship('IceBatch', backref='inventory_flows')

    FLOW_TYPE_LABELS = {
        'entry': '入窖',
        'transfer_out': '调拨出库',
        'transfer_in': '调拨入库',
        'outbound': '出窖',
        'melt_loss': '融损',
        'adjust': '库存调整',
    }

    def flow_type_label(self):
        return self.FLOW_TYPE_LABELS.get(self.flow_type, self.flow_type)


class InventoryForecast(db.Model):
    __tablename__ = 'inventory_forecasts'
    id = db.Column(db.Integer, primary_key=True)
    ice_house_id = db.Column(db.Integer, db.ForeignKey('ice_houses.id'), nullable=False)
    forecast_date = db.Column(db.Date, nullable=False)
    current_total = db.Column(db.Integer, nullable=False)
    daily_melt_rate = db.Column(db.Float, default=0)
    daily_outbound_rate = db.Column(db.Float, default=0)
    daily_consumption_rate = db.Column(db.Float, default=0)
    available_days = db.Column(db.Float, default=0)
    forecast_30d = db.Column(db.Integer, default=0)
    forecast_7d = db.Column(db.Integer, default=0)
    avg_temperature = db.Column(db.Float)
    avg_humidity = db.Column(db.Float)
    method = db.Column(db.String(50), default='hybrid')
    confidence = db.Column(db.Float, default=0.7)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ice_house = db.relationship('IceHouse', backref='inventory_forecasts')


class InventoryAlert(db.Model):
    __tablename__ = 'inventory_alerts'
    id = db.Column(db.Integer, primary_key=True)
    ice_house_id = db.Column(db.Integer, db.ForeignKey('ice_houses.id'), nullable=False)
    alert_type = db.Column(db.String(30), nullable=False)
    severity = db.Column(db.String(20), default='medium')
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    current_stock = db.Column(db.Integer)
    threshold = db.Column(db.Integer)
    available_days = db.Column(db.Float)
    status = db.Column(db.String(20), default='active')
    source_type = db.Column(db.String(50))
    source_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)
    resolved_by = db.Column(db.String(100))
    resolve_note = db.Column(db.Text)

    ice_house = db.relationship('IceHouse', backref='inventory_alerts')

    ALERT_TYPE_LABELS = {
        'shortage': '缺冰预警',
        'surplus': '压库存预警',
        'critical_shortage': '严重缺冰',
    }

    def alert_type_label(self):
        return self.ALERT_TYPE_LABELS.get(self.alert_type, self.alert_type)


class TransferRecommendation(db.Model):
    __tablename__ = 'transfer_recommendations'
    id = db.Column(db.Integer, primary_key=True)
    rec_no = db.Column(db.String(50), unique=True, nullable=False)
    from_house_id = db.Column(db.Integer, db.ForeignKey('ice_houses.id'), nullable=False)
    to_house_id = db.Column(db.Integer, db.ForeignKey('ice_houses.id'), nullable=False)
    recommended_quantity = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.Text)
    reason_details = db.Column(db.Text)
    priority = db.Column(db.String(20), default='medium')
    status = db.Column(db.String(20), default='pending')
    confidence_score = db.Column(db.Float, default=0.0)
    shortage_days = db.Column(db.Float)
    surplus_days = db.Column(db.Float)
    from_house_available_days = db.Column(db.Float)
    to_house_available_days = db.Column(db.Float)

    applicant = db.Column(db.String(100))
    apply_date = db.Column(db.Date)
    approver = db.Column(db.String(100))
    approval_date = db.Column(db.Date)
    approval_comment = db.Column(db.Text)

    executor = db.Column(db.String(100))
    execute_date = db.Column(db.Date)
    actual_quantity = db.Column(db.Integer)
    execute_remark = db.Column(db.Text)

    transfer_order_id = db.Column(db.Integer, db.ForeignKey('transfer_orders.id'))
    is_hit = db.Column(db.Boolean)
    hit_score = db.Column(db.Float)

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    from_house = db.relationship('IceHouse', foreign_keys=[from_house_id], backref='outgoing_recommendations')
    to_house = db.relationship('IceHouse', foreign_keys=[to_house_id], backref='incoming_recommendations')
    transfer_order = db.relationship('TransferOrder', backref='recommendation')

    STATUS_LABELS = {
        'pending': '待审批',
        'approved': '已批准',
        'rejected': '已驳回',
        'executing': '执行中',
        'completed': '已完成',
        'cancelled': '已取消',
    }

    PRIORITY_LABELS = {
        'low': '低',
        'medium': '中',
        'high': '高',
        'urgent': '紧急',
    }

    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    def priority_label(self):
        return self.PRIORITY_LABELS.get(self.priority, self.priority)
