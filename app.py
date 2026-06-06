import os
from datetime import datetime, date
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, abort
)
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user
)

from models import (
    db, User, IceHouse, IceBatch, Inspection, MeltLoss, Repair,
    RiskAlert, RectificationTask, ReviewRecord, ApprovalRequest, Notification,
    TransferOrder, TransferItem, OutboundRecord, InventoryFlow
)


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'icehouse-secret-key-2024'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///icehouse.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = '请先登录系统'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    def htmx_response(template_name, **context):
        if request.headers.get('HX-Request'):
            return render_template(template_name, **context)
        return render_template(template_name, **context)

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('index'))

        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            user = User.query.filter_by(username=username).first()

            if user and user.check_password(password):
                login_user(user)
                flash('登录成功', 'success')
                return redirect(url_for('index'))
            flash('用户名或密码错误', 'danger')

        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('已退出登录', 'info')
        return redirect(url_for('login'))

    @app.route('/')
    @login_required
    def index():
        total_houses = IceHouse.query.count()
        open_houses = IceHouse.query.filter_by(is_open=True).count()
        high_risk_houses = IceHouse.query.filter_by(high_risk=True).count()
        total_batches = IceBatch.query.count()
        total_inspections = Inspection.query.count()
        pending_repairs = Repair.query.filter(Repair.status != 'completed').count()

        active_alerts = RiskAlert.query.filter_by(status='active').count()
        pending_rectifications = RectificationTask.query.filter(
            RectificationTask.status.in_(['pending', 'in_progress'])
        ).count()
        pending_reviews = RectificationTask.query.filter_by(status='completed').filter(
            ~RectificationTask.reviews.any(ReviewRecord.result == 'pass')
        ).count()
        pending_approvals = ApprovalRequest.query.filter_by(status='pending').count()

        recent_inspections = Inspection.query.order_by(
            Inspection.inspection_date.desc()
        ).limit(5).all()

        recent_repairs = Repair.query.order_by(
            Repair.report_date.desc()
        ).limit(5).all()

        recent_alerts = RiskAlert.query.order_by(
            RiskAlert.created_at.desc()
        ).limit(5).all()

        recent_rectifications = RectificationTask.query.order_by(
            RectificationTask.created_at.desc()
        ).limit(5).all()

        return render_template('index.html',
                               total_houses=total_houses,
                               open_houses=open_houses,
                               high_risk_houses=high_risk_houses,
                               total_batches=total_batches,
                               total_inspections=total_inspections,
                               pending_repairs=pending_repairs,
                               active_alerts=active_alerts,
                               pending_rectifications=pending_rectifications,
                               pending_reviews=pending_reviews,
                               pending_approvals=pending_approvals,
                               recent_inspections=recent_inspections,
                               recent_repairs=recent_repairs,
                               recent_alerts=recent_alerts,
                               recent_rectifications=recent_rectifications)

    @app.route('/icehouses')
    @login_required
    def icehouses():
        houses = IceHouse.query.order_by(IceHouse.code).all()
        return render_template('icehouses/list.html', houses=houses)

    @app.route('/icehouses/new', methods=['GET', 'POST'])
    @login_required
    def icehouse_new():
        if request.method == 'POST':
            code = request.form.get('code', '').strip()
            location = request.form.get('location', '').strip()
            build_year = request.form.get('build_year')
            capacity = request.form.get('capacity', type=int)
            is_open = request.form.get('is_open') == 'on'

            if not code or not location or not capacity:
                flash('请填写完整信息', 'danger')
                return render_template('icehouses/form.html', house=None)

            if IceHouse.query.filter_by(code=code).first():
                flash('冰窖编号已存在', 'danger')
                return render_template('icehouses/form.html', house=None)

            house = IceHouse(
                code=code,
                location=location,
                build_year=int(build_year) if build_year else None,
                capacity=capacity,
                is_open=is_open
            )
            db.session.add(house)
            db.session.commit()
            flash('冰窖档案创建成功', 'success')
            return redirect(url_for('icehouse_detail', house_id=house.id))

        return render_template('icehouses/form.html', house=None)

    @app.route('/icehouses/<int:house_id>')
    @login_required
    def icehouse_detail(house_id):
        house = IceHouse.query.get_or_404(house_id)
        batches = IceBatch.query.filter_by(ice_house_id=house_id).order_by(
            IceBatch.entry_date.desc()
        ).all()
        inspections = Inspection.query.filter_by(ice_house_id=house_id).order_by(
            Inspection.inspection_date.desc()
        ).limit(10).all()
        repairs = Repair.query.filter_by(ice_house_id=house_id).order_by(
            Repair.report_date.desc()
        ).all()
        return render_template('icehouses/detail.html',
                               house=house, batches=batches,
                               inspections=inspections, repairs=repairs)

    @app.route('/icehouses/<int:house_id>/edit', methods=['GET', 'POST'])
    @login_required
    def icehouse_edit(house_id):
        house = IceHouse.query.get_or_404(house_id)

        if request.method == 'POST':
            code = request.form.get('code', '').strip()
            location = request.form.get('location', '').strip()
            build_year = request.form.get('build_year')
            capacity = request.form.get('capacity', type=int)
            is_open = request.form.get('is_open') == 'on'

            if not code or not location or not capacity:
                flash('请填写完整信息', 'danger')
                return render_template('icehouses/form.html', house=house)

            existing = IceHouse.query.filter_by(code=code).first()
            if existing and existing.id != house_id:
                flash('冰窖编号已存在', 'danger')
                return render_template('icehouses/form.html', house=house)

            if is_open:
                can_open, msg = house.can_be_opened()
                if not can_open:
                    flash(f'不能设置为开放状态：{msg}', 'danger')
                    return render_template('icehouses/form.html', house=house)

            house.code = code
            house.location = location
            house.build_year = int(build_year) if build_year else None
            house.capacity = capacity
            house.is_open = is_open
            db.session.commit()
            flash('冰窖档案更新成功', 'success')
            return redirect(url_for('icehouse_detail', house_id=house.id))

        return render_template('icehouses/form.html', house=house)

    @app.route('/icehouses/<int:house_id>/delete', methods=['POST'])
    @login_required
    def icehouse_delete(house_id):
        house = IceHouse.query.get_or_404(house_id)
        db.session.delete(house)
        db.session.commit()
        flash('冰窖档案已删除', 'info')
        return redirect(url_for('icehouses'))

    @app.route('/batches')
    @login_required
    def batches():
        all_batches = IceBatch.query.order_by(IceBatch.entry_date.desc()).all()
        return render_template('batches/list.html', batches=all_batches)

    @app.route('/batches/new', methods=['GET', 'POST'])
    @login_required
    def batch_new():
        houses = IceHouse.query.order_by(IceHouse.code).all()

        if request.method == 'POST':
            ice_house_id = request.form.get('ice_house_id', type=int)
            entry_date_str = request.form.get('entry_date')
            ice_count = request.form.get('ice_count', type=int)
            expected_storage_period = request.form.get('expected_storage_period', type=int)
            current_remaining = request.form.get('current_remaining', type=int)

            if not ice_house_id or not entry_date_str or not ice_count or not expected_storage_period:
                flash('请填写完整信息', 'danger')
                return render_template('batches/form.html', batch=None, houses=houses)

            entry_date = datetime.strptime(entry_date_str, '%Y-%m-%d').date()
            if entry_date > date.today():
                flash('入窖日期不能晚于当前日期', 'danger')
                return render_template('batches/form.html', batch=None, houses=houses)

            if current_remaining is None:
                current_remaining = ice_count

            if current_remaining < 0:
                flash('当前剩余量不能为负数', 'danger')
                return render_template('batches/form.html', batch=None, houses=houses)

            if current_remaining > ice_count:
                flash('当前剩余量不能大于入窖数量', 'danger')
                return render_template('batches/form.html', batch=None, houses=houses)

            batch = IceBatch(
                ice_house_id=ice_house_id,
                entry_date=entry_date,
                ice_count=ice_count,
                expected_storage_period=expected_storage_period,
                current_remaining=current_remaining
            )
            db.session.add(batch)
            db.session.commit()
            flash('藏冰批次创建成功', 'success')
            return redirect(url_for('batches'))

        return render_template('batches/form.html', batch=None, houses=houses)

    @app.route('/batches/<int:batch_id>/edit', methods=['GET', 'POST'])
    @login_required
    def batch_edit(batch_id):
        batch = IceBatch.query.get_or_404(batch_id)
        houses = IceHouse.query.order_by(IceHouse.code).all()

        if request.method == 'POST':
            ice_house_id = request.form.get('ice_house_id', type=int)
            entry_date_str = request.form.get('entry_date')
            ice_count = request.form.get('ice_count', type=int)
            expected_storage_period = request.form.get('expected_storage_period', type=int)
            current_remaining = request.form.get('current_remaining', type=int)

            if not ice_house_id or not entry_date_str or not ice_count or not expected_storage_period:
                flash('请填写完整信息', 'danger')
                return render_template('batches/form.html', batch=batch, houses=houses)

            entry_date = datetime.strptime(entry_date_str, '%Y-%m-%d').date()
            if entry_date > date.today():
                flash('入窖日期不能晚于当前日期', 'danger')
                return render_template('batches/form.html', batch=batch, houses=houses)

            if current_remaining is None:
                current_remaining = ice_count

            if current_remaining < 0:
                flash('当前剩余量不能为负数', 'danger')
                return render_template('batches/form.html', batch=batch, houses=houses)

            if current_remaining > ice_count:
                flash('当前剩余量不能大于入窖数量', 'danger')
                return render_template('batches/form.html', batch=batch, houses=houses)

            batch.ice_house_id = ice_house_id
            batch.entry_date = entry_date
            batch.ice_count = ice_count
            batch.expected_storage_period = expected_storage_period
            batch.current_remaining = current_remaining
            db.session.commit()
            flash('藏冰批次更新成功', 'success')
            return redirect(url_for('batches'))

        return render_template('batches/form.html', batch=batch, houses=houses)

    @app.route('/batches/<int:batch_id>/delete', methods=['POST'])
    @login_required
    def batch_delete(batch_id):
        batch = IceBatch.query.get_or_404(batch_id)
        db.session.delete(batch)
        db.session.commit()
        flash('藏冰批次已删除', 'info')
        return redirect(url_for('batches'))

    @app.route('/inspections')
    @login_required
    def inspections():
        all_inspections = Inspection.query.order_by(
            Inspection.inspection_date.desc()
        ).all()
        return render_template('inspections/list.html', inspections=all_inspections)

    @app.route('/inspections/new', methods=['GET', 'POST'])
    @login_required
    def inspection_new():
        houses = IceHouse.query.order_by(IceHouse.code).all()

        if request.method == 'POST':
            ice_house_id = request.form.get('ice_house_id', type=int)
            inspection_date_str = request.form.get('inspection_date')
            temperature = request.form.get('temperature', type=float)
            humidity = request.form.get('humidity', type=float)
            seepage = request.form.get('seepage') == 'on'
            melt_level = request.form.get('melt_level', 'normal')
            suggestions = request.form.get('suggestions', '').strip()

            if not ice_house_id or not inspection_date_str or temperature is None or humidity is None:
                flash('请填写完整信息', 'danger')
                return render_template('inspections/form.html', inspection=None, houses=houses)

            inspection_date = datetime.strptime(inspection_date_str, '%Y-%m-%d').date()
            if inspection_date > date.today():
                flash('巡检日期不能晚于当前日期', 'danger')
                return render_template('inspections/form.html', inspection=None, houses=houses)

            inspection = Inspection(
                ice_house_id=ice_house_id,
                inspection_date=inspection_date,
                temperature=temperature,
                humidity=humidity,
                seepage=seepage,
                melt_level=melt_level,
                suggestions=suggestions
            )
            db.session.add(inspection)
            db.session.flush()

            house = IceHouse.query.get(ice_house_id)
            has_seepage, has_severe_melt = house.update_risk_status()

            if has_seepage:
                alert = create_risk_alert(
                    ice_house_id, 'seepage', 'high',
                    '冰窖渗水风险', f'巡检发现冰窖 {house.code} 存在渗水现象',
                    'inspection', inspection.id
                )
                auto_create_rectification(alert)

            if has_severe_melt:
                alert = create_risk_alert(
                    ice_house_id, 'severe_melt', 'high',
                    '严重融损风险', f'巡检发现冰窖 {house.code} 融损情况严重',
                    'inspection', inspection.id
                )
                auto_create_rectification(alert)

            db.session.commit()
            flash('巡检记录创建成功', 'success')
            return redirect(url_for('inspections'))

        return render_template('inspections/form.html', inspection=None, houses=houses)

    @app.route('/inspections/<int:inspection_id>/edit', methods=['GET', 'POST'])
    @login_required
    def inspection_edit(inspection_id):
        inspection = Inspection.query.get_or_404(inspection_id)
        houses = IceHouse.query.order_by(IceHouse.code).all()

        if request.method == 'POST':
            ice_house_id = request.form.get('ice_house_id', type=int)
            inspection_date_str = request.form.get('inspection_date')
            temperature = request.form.get('temperature', type=float)
            humidity = request.form.get('humidity', type=float)
            seepage = request.form.get('seepage') == 'on'
            melt_level = request.form.get('melt_level', 'normal')
            suggestions = request.form.get('suggestions', '').strip()

            if not ice_house_id or not inspection_date_str or temperature is None or humidity is None:
                flash('请填写完整信息', 'danger')
                return render_template('inspections/form.html', inspection=inspection, houses=houses)

            inspection_date = datetime.strptime(inspection_date_str, '%Y-%m-%d').date()
            if inspection_date > date.today():
                flash('巡检日期不能晚于当前日期', 'danger')
                return render_template('inspections/form.html', inspection=inspection, houses=houses)

            inspection.ice_house_id = ice_house_id
            inspection.inspection_date = inspection_date
            inspection.temperature = temperature
            inspection.humidity = humidity
            inspection.seepage = seepage
            inspection.melt_level = melt_level
            inspection.suggestions = suggestions

            house = IceHouse.query.get(ice_house_id)
            has_seepage, has_severe_melt = house.update_risk_status()

            if has_seepage:
                alert = create_risk_alert(
                    ice_house_id, 'seepage', 'high',
                    '冰窖渗水风险', f'巡检发现冰窖 {house.code} 存在渗水现象',
                    'inspection', inspection.id
                )
                auto_create_rectification(alert)

            if has_severe_melt:
                alert = create_risk_alert(
                    ice_house_id, 'severe_melt', 'high',
                    '严重融损风险', f'巡检发现冰窖 {house.code} 融损情况严重',
                    'inspection', inspection.id
                )
                auto_create_rectification(alert)

            db.session.commit()
            flash('巡检记录更新成功', 'success')
            return redirect(url_for('inspections'))

        return render_template('inspections/form.html', inspection=inspection, houses=houses)

    @app.route('/inspections/<int:inspection_id>/delete', methods=['POST'])
    @login_required
    def inspection_delete(inspection_id):
        inspection = Inspection.query.get_or_404(inspection_id)
        ice_house_id = inspection.ice_house_id
        db.session.delete(inspection)
        db.session.flush()

        house = IceHouse.query.get(ice_house_id)
        house.update_risk_status()

        db.session.commit()
        flash('巡检记录已删除', 'info')
        return redirect(url_for('inspections'))

    @app.route('/melt-losses')
    @login_required
    def melt_losses():
        all_losses = MeltLoss.query.order_by(MeltLoss.record_date.desc()).all()
        return render_template('melt_losses/list.html', losses=all_losses)

    @app.route('/melt-losses/new', methods=['GET', 'POST'])
    @login_required
    def melt_loss_new():
        houses = IceHouse.query.order_by(IceHouse.code).all()
        batches = IceBatch.query.order_by(IceBatch.entry_date.desc()).all()

        if request.method == 'POST':
            ice_house_id = request.form.get('ice_house_id', type=int)
            batch_id = request.form.get('batch_id', type=int)
            record_date_str = request.form.get('record_date')
            loss_amount = request.form.get('loss_amount', type=int)
            reason = request.form.get('reason', '').strip()

            if not ice_house_id or not batch_id or not record_date_str or not loss_amount:
                flash('请填写完整信息', 'danger')
                return render_template('melt_losses/form.html', loss=None, houses=houses, batches=batches)

            record_date = datetime.strptime(record_date_str, '%Y-%m-%d').date()
            if record_date > date.today():
                flash('记录日期不能晚于当前日期', 'danger')
                return render_template('melt_losses/form.html', loss=None, houses=houses, batches=batches)

            batch = IceBatch.query.get(batch_id)
            if not batch:
                flash('批次不存在', 'danger')
                return render_template('melt_losses/form.html', loss=None, houses=houses, batches=batches)

            if batch.ice_house_id != ice_house_id:
                flash('该批次不属于所选冰窖', 'danger')
                return render_template('melt_losses/form.html', loss=None, houses=houses, batches=batches)

            if loss_amount > batch.current_remaining:
                flash('融损数量不能大于当前剩余量', 'danger')
                return render_template('melt_losses/form.html', loss=None, houses=houses, batches=batches)

            loss = MeltLoss(
                ice_house_id=ice_house_id,
                batch_id=batch_id,
                record_date=record_date,
                loss_amount=loss_amount,
                reason=reason
            )
            batch.current_remaining -= loss_amount
            db.session.add(loss)
            db.session.commit()
            flash('融损登记成功', 'success')
            return redirect(url_for('melt_losses'))

        return render_template('melt_losses/form.html', loss=None, houses=houses, batches=batches)

    @app.route('/melt-losses/<int:loss_id>/delete', methods=['POST'])
    @login_required
    def melt_loss_delete(loss_id):
        loss = MeltLoss.query.get_or_404(loss_id)
        batch = IceBatch.query.get(loss.batch_id)
        if batch:
            batch.current_remaining += loss.loss_amount
        db.session.delete(loss)
        db.session.commit()
        flash('融损记录已删除', 'info')
        return redirect(url_for('melt_losses'))

    @app.route('/repairs')
    @login_required
    def repairs():
        all_repairs = Repair.query.order_by(Repair.report_date.desc()).all()
        return render_template('repairs/list.html', repairs=all_repairs)

    @app.route('/repairs/new', methods=['GET', 'POST'])
    @login_required
    def repair_new():
        houses = IceHouse.query.order_by(IceHouse.code).all()

        if request.method == 'POST':
            ice_house_id = request.form.get('ice_house_id', type=int)
            report_date_str = request.form.get('report_date')
            issue_description = request.form.get('issue_description', '').strip()

            if not ice_house_id or not report_date_str or not issue_description:
                flash('请填写完整信息', 'danger')
                return render_template('repairs/form.html', repair=None, houses=houses)

            report_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
            if report_date > date.today():
                flash('报修日期不能晚于当前日期', 'danger')
                return render_template('repairs/form.html', repair=None, houses=houses)

            repair = Repair(
                ice_house_id=ice_house_id,
                report_date=report_date,
                issue_description=issue_description,
                status='pending'
            )
            db.session.add(repair)
            db.session.commit()
            flash('修缮工单创建成功', 'success')
            return redirect(url_for('repairs'))

        return render_template('repairs/form.html', repair=None, houses=houses)

    @app.route('/repairs/<int:repair_id>/edit', methods=['GET', 'POST'])
    @login_required
    def repair_edit(repair_id):
        repair = Repair.query.get_or_404(repair_id)
        houses = IceHouse.query.order_by(IceHouse.code).all()

        if request.method == 'POST':
            ice_house_id = request.form.get('ice_house_id', type=int)
            report_date_str = request.form.get('report_date')
            issue_description = request.form.get('issue_description', '').strip()
            status = request.form.get('status', 'pending')
            repair_date_str = request.form.get('repair_date')
            repair_cost = request.form.get('repair_cost', type=float)
            notes = request.form.get('notes', '').strip()

            if not ice_house_id or not report_date_str or not issue_description:
                flash('请填写完整信息', 'danger')
                return render_template('repairs/form.html', repair=repair, houses=houses)

            report_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
            if report_date > date.today():
                flash('报修日期不能晚于当前日期', 'danger')
                return render_template('repairs/form.html', repair=repair, houses=houses)

            if repair_date_str:
                repair_date = datetime.strptime(repair_date_str, '%Y-%m-%d').date()
                if repair_date > date.today():
                    flash('修缮日期不能晚于当前日期', 'danger')
                    return render_template('repairs/form.html', repair=repair, houses=houses)

            repair.ice_house_id = ice_house_id
            repair.report_date = report_date
            repair.issue_description = issue_description
            repair.status = status
            repair.repair_date = datetime.strptime(repair_date_str, '%Y-%m-%d').date() if repair_date_str else None
            repair.repair_cost = repair_cost if repair_cost else 0
            repair.notes = notes

            db.session.commit()
            flash('修缮工单更新成功', 'success')
            return redirect(url_for('repairs'))

        return render_template('repairs/form.html', repair=repair, houses=houses)

    @app.route('/repairs/<int:repair_id>/delete', methods=['POST'])
    @login_required
    def repair_delete(repair_id):
        repair = Repair.query.get_or_404(repair_id)
        db.session.delete(repair)
        db.session.commit()
        flash('修缮工单已删除', 'info')
        return redirect(url_for('repairs'))

    @app.route('/api/batches/by-house/<int:house_id>')
    @login_required
    def api_batches_by_house(house_id):
        batches = IceBatch.query.filter_by(ice_house_id=house_id).order_by(
            IceBatch.entry_date.desc()
        ).all()
        return jsonify([
            {'id': b.id, 'label': f'{b.entry_date} - {b.ice_count}块 (剩余{b.current_remaining})'}
            for b in batches
        ])

    def generate_task_no():
        from datetime import datetime as dt
        prefix = 'ZG' + dt.now().strftime('%Y%m%d')
        count = RectificationTask.query.filter(
            RectificationTask.task_no.like(prefix + '%')
        ).count()
        return f'{prefix}{count + 1:03d}'

    def create_notification(user_id, type, title, content, related_type=None, related_id=None):
        notification = Notification(
            user_id=user_id,
            type=type,
            title=title,
            content=content,
            related_type=related_type,
            related_id=related_id
        )
        db.session.add(notification)

    def create_risk_alert(ice_house_id, alert_type, severity, title, description, source_type=None, source_id=None):
        existing = RiskAlert.query.filter_by(
            ice_house_id=ice_house_id,
            alert_type=alert_type,
            source_type=source_type,
            source_id=source_id,
            status='active'
        ).first()
        if existing:
            return existing
        alert = RiskAlert(
            ice_house_id=ice_house_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            description=description,
            source_type=source_type,
            source_id=source_id
        )
        db.session.add(alert)
        db.session.flush()

        admin = User.query.filter_by(username='admin').first()
        if admin:
            create_notification(
                admin.id, 'risk', f'新风险预警：{title}',
                f'冰窖 {alert.ice_house.code} 触发风险预警：{title}',
                'risk_alert', alert.id
            )
        return alert

    def auto_create_rectification(alert):
        existing = RectificationTask.query.filter_by(
            risk_alert_id=alert.id,
            status='pending'
        ).first()
        if existing:
            return existing

        task = RectificationTask(
            ice_house_id=alert.ice_house_id,
            risk_alert_id=alert.id,
            task_no=generate_task_no(),
            title=f'整改：{alert.title}',
            description=alert.description,
            requirement='请尽快完成整改，消除安全隐患',
            status='pending'
        )
        db.session.add(task)
        db.session.flush()

        admin = User.query.filter_by(username='admin').first()
        if admin:
            create_notification(
                admin.id, 'rectification',
                f'新整改任务：{task.title}',
                f'冰窖 {alert.ice_house.code} 产生新的整改任务：{task.title}',
                'rectification', task.id
            )
        return task

    # ========== 风险预警中心 ==========
    @app.route('/risk-alerts')
    @login_required
    def risk_alerts():
        status = request.args.get('status', '')
        severity = request.args.get('severity', '')
        ice_house_id = request.args.get('ice_house_id', type=int)

        query = RiskAlert.query
        if status:
            query = query.filter_by(status=status)
        if severity:
            query = query.filter_by(severity=severity)
        if ice_house_id:
            query = query.filter_by(ice_house_id=ice_house_id)

        alerts = query.order_by(RiskAlert.created_at.desc()).all()
        houses = IceHouse.query.order_by(IceHouse.code).all()
        return render_template('risk_alerts/list.html', alerts=alerts, houses=houses)

    @app.route('/risk-alerts/<int:alert_id>')
    @login_required
    def risk_alert_detail(alert_id):
        alert = RiskAlert.query.get_or_404(alert_id)
        return render_template('risk_alerts/detail.html', alert=alert)

    @app.route('/risk-alerts/<int:alert_id>/resolve', methods=['POST'])
    @login_required
    def risk_alert_resolve(alert_id):
        alert = RiskAlert.query.get_or_404(alert_id)
        alert.status = 'resolved'
        alert.resolved_at = datetime.utcnow()
        db.session.commit()
        flash('风险已解除', 'success')
        return redirect(url_for('risk_alert_detail', alert_id=alert_id))

    # ========== 整改任务 ==========
    @app.route('/rectifications')
    @login_required
    def rectifications():
        status = request.args.get('status', '')
        ice_house_id = request.args.get('ice_house_id', type=int)

        query = RectificationTask.query
        if status:
            query = query.filter_by(status=status)
        if ice_house_id:
            query = query.filter_by(ice_house_id=ice_house_id)

        tasks = query.order_by(RectificationTask.created_at.desc()).all()
        houses = IceHouse.query.order_by(IceHouse.code).all()
        return render_template('rectifications/list.html', tasks=tasks, houses=houses)

    @app.route('/rectifications/new', methods=['GET', 'POST'])
    @login_required
    def rectification_new():
        houses = IceHouse.query.order_by(IceHouse.code).all()
        alerts = RiskAlert.query.filter_by(status='active').all()

        if request.method == 'POST':
            ice_house_id = request.form.get('ice_house_id', type=int)
            risk_alert_id = request.form.get('risk_alert_id', type=int) or None
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            requirement = request.form.get('requirement', '').strip()
            deadline_str = request.form.get('deadline')
            assigned_to = request.form.get('assigned_to', '').strip()

            if not ice_house_id or not title:
                flash('请填写必填信息', 'danger')
                return render_template('rectifications/form.html', task=None, houses=houses, alerts=alerts)

            deadline = None
            if deadline_str:
                deadline = datetime.strptime(deadline_str, '%Y-%m-%d').date()
                if deadline < date.today():
                    flash('截止日期不能早于今天', 'danger')
                    return render_template('rectifications/form.html', task=None, houses=houses, alerts=alerts)

            task = RectificationTask(
                ice_house_id=ice_house_id,
                risk_alert_id=risk_alert_id,
                task_no=generate_task_no(),
                title=title,
                description=description,
                requirement=requirement,
                deadline=deadline,
                assigned_to=assigned_to,
                status='pending',
                created_by=current_user.id
            )
            db.session.add(task)
            db.session.commit()
            flash('整改任务创建成功', 'success')
            return redirect(url_for('rectification_detail', task_id=task.id))

        return render_template('rectifications/form.html', task=None, houses=houses, alerts=alerts)

    @app.route('/rectifications/<int:task_id>')
    @login_required
    def rectification_detail(task_id):
        task = RectificationTask.query.get_or_404(task_id)
        reviews = ReviewRecord.query.filter_by(rectification_task_id=task_id).order_by(
            ReviewRecord.created_at.desc()
        ).all()
        return render_template('rectifications/detail.html', task=task, reviews=reviews)

    @app.route('/rectifications/<int:task_id>/start', methods=['POST'])
    @login_required
    def rectification_start(task_id):
        task = RectificationTask.query.get_or_404(task_id)
        if task.status != 'pending':
            flash('任务状态不允许开始', 'danger')
            return redirect(url_for('rectification_detail', task_id=task_id))
        task.status = 'in_progress'
        db.session.commit()
        flash('整改任务已开始', 'success')
        return redirect(url_for('rectification_detail', task_id=task_id))

    @app.route('/rectifications/<int:task_id>/complete', methods=['GET', 'POST'])
    @login_required
    def rectification_complete(task_id):
        task = RectificationTask.query.get_or_404(task_id)

        if request.method == 'POST':
            result = request.form.get('rectification_result', '').strip()
            finish_date_str = request.form.get('actual_finish_date')

            if not result:
                flash('请填写整改结果', 'danger')
                return render_template('rectifications/complete.html', task=task)

            finish_date = date.today()
            if finish_date_str:
                finish_date = datetime.strptime(finish_date_str, '%Y-%m-%d').date()

            task.status = 'completed'
            task.rectification_result = result
            task.actual_finish_date = finish_date
            db.session.commit()

            admin = User.query.filter_by(username='admin').first()
            if admin:
                create_notification(
                    admin.id, 'review',
                    f'整改待复核：{task.title}',
                    f'冰窖 {task.ice_house.code} 的整改任务已完成，请安排复核',
                    'rectification', task.id
                )

            flash('整改已完成，请等待复核', 'success')
            return redirect(url_for('rectification_detail', task_id=task_id))

        return render_template('rectifications/complete.html', task=task)

    # ========== 复核记录 ==========
    @app.route('/reviews')
    @login_required
    def reviews():
        status = request.args.get('status', 'pending')
        if status == 'pending':
            tasks = RectificationTask.query.filter_by(status='completed').filter(
                ~RectificationTask.reviews.any(ReviewRecord.result == 'pass')
            ).order_by(RectificationTask.updated_at.desc()).all()
        else:
            all_tasks = RectificationTask.query.filter(RectificationTask.reviews.any()).all()
            tasks = [t for t in all_tasks if any(r.result == 'pass' for r in t.reviews)]

        return render_template('reviews/list.html', tasks=tasks, status=status)

    @app.route('/rectifications/<int:task_id>/review', methods=['GET', 'POST'])
    @login_required
    def review_create(task_id):
        task = RectificationTask.query.get_or_404(task_id)

        if request.method == 'POST':
            result = request.form.get('result', '')
            comment = request.form.get('comment', '').strip()
            reviewer = request.form.get('reviewer', '').strip()
            review_date_str = request.form.get('review_date')

            if not result:
                flash('请选择复核结果', 'danger')
                return render_template('reviews/form.html', task=task)

            review_date = date.today()
            if review_date_str:
                review_date = datetime.strptime(review_date_str, '%Y-%m-%d').date()

            review = ReviewRecord(
                rectification_task_id=task_id,
                review_date=review_date,
                reviewer=reviewer or current_user.username,
                result=result,
                comment=comment
            )
            db.session.add(review)

            if result == 'pass':
                task.status = 'reviewed'
                if task.risk_alert:
                    task.risk_alert.status = 'resolved'
                    task.risk_alert.resolved_at = datetime.utcnow()
                task.ice_house.update_risk_status()

                admin = User.query.filter_by(username='admin').first()
                if admin:
                    create_notification(
                        admin.id, 'review',
                        f'复核通过：{task.title}',
                        f'冰窖 {task.ice_house.code} 的整改任务复核通过',
                        'rectification', task.id
                    )
            else:
                task.status = 'rejected'

                admin = User.query.filter_by(username='admin').first()
                if admin:
                    create_notification(
                        admin.id, 'review',
                        f'复核未通过：{task.title}',
                        f'冰窖 {task.ice_house.code} 的整改任务复核未通过，请重新整改',
                        'rectification', task.id
                    )

            db.session.commit()
            flash('复核记录已提交', 'success')
            return redirect(url_for('rectification_detail', task_id=task_id))

        return render_template('reviews/form.html', task=task)

    # ========== 开放审批流 ==========
    @app.route('/approvals')
    @login_required
    def approvals():
        status = request.args.get('status', '')
        query = ApprovalRequest.query
        if status:
            query = query.filter_by(status=status)
        requests = query.order_by(ApprovalRequest.created_at.desc()).all()
        return render_template('approvals/list.html', requests=requests)

    @app.route('/approvals/new', methods=['GET', 'POST'])
    @login_required
    def approval_new():
        houses = IceHouse.query.order_by(IceHouse.code).all()

        if request.method == 'POST':
            ice_house_id = request.form.get('ice_house_id', type=int)
            reason = request.form.get('reason', '').strip()
            applicant = request.form.get('applicant', '').strip()
            request_type = request.form.get('request_type', 'open')

            if not ice_house_id:
                flash('请选择冰窖', 'danger')
                return render_template('approvals/form.html', request=None, houses=houses)

            house = IceHouse.query.get(ice_house_id)
            if not house:
                flash('冰窖不存在', 'danger')
                return render_template('approvals/form.html', request=None, houses=houses)

            if request_type == 'open' and house.is_open:
                flash('冰窖已处于开放状态', 'warning')
                return render_template('approvals/form.html', request=None, houses=houses)

            can_open, msg = house.can_be_opened()
            if request_type == 'open' and not can_open:
                flash(f'无法申请开放：{msg}', 'danger')
                return render_template('approvals/form.html', request=None, houses=houses)

            title = f'{"开放" if request_type == "open" else "关闭"}冰窖申请：{house.code}'

            approval = ApprovalRequest(
                ice_house_id=ice_house_id,
                request_type=request_type,
                title=title,
                reason=reason,
                applicant=applicant or current_user.username,
                apply_date=date.today(),
                status='pending'
            )
            db.session.add(approval)
            db.session.commit()

            admin = User.query.filter_by(username='admin').first()
            if admin:
                create_notification(
                    admin.id, 'approval',
                    f'新审批申请：{title}',
                    f'冰窖 {house.code} 有新的{"开放" if request_type == "open" else "关闭"}申请，请处理',
                    'approval', approval.id
                )

            flash('审批申请已提交', 'success')
            return redirect(url_for('approval_detail', request_id=approval.id))

        return render_template('approvals/form.html', request=None, houses=houses)

    @app.route('/approvals/<int:request_id>')
    @login_required
    def approval_detail(request_id):
        req = ApprovalRequest.query.get_or_404(request_id)
        return render_template('approvals/detail.html', request=req)

    @app.route('/approvals/<int:request_id>/approve', methods=['POST'])
    @login_required
    def approval_approve(request_id):
        req = ApprovalRequest.query.get_or_404(request_id)
        if req.status != 'pending':
            flash('申请已处理', 'warning')
            return redirect(url_for('approval_detail', request_id=request_id))

        comment = request.form.get('approval_comment', '').strip()

        if req.request_type == 'open':
            can_open, msg = req.ice_house.can_be_opened()
            if not can_open:
                flash(f'无法开放：{msg}', 'danger')
                return redirect(url_for('approval_detail', request_id=request_id))
            req.ice_house.is_open = True
        else:
            req.ice_house.is_open = False

        req.status = 'approved'
        req.approver = current_user.username
        req.approval_date = date.today()
        req.approval_comment = comment

        create_notification(
            None, 'approval',
            f'审批通过：{req.title}',
            f'冰窖 {req.ice_house.code} 的{"开放" if req.request_type == "open" else "关闭"}申请已通过',
            'approval', req.id
        )

        db.session.commit()
        flash('审批已通过', 'success')
        return redirect(url_for('approval_detail', request_id=request_id))

    @app.route('/approvals/<int:request_id>/reject', methods=['POST'])
    @login_required
    def approval_reject(request_id):
        req = ApprovalRequest.query.get_or_404(request_id)
        if req.status != 'pending':
            flash('申请已处理', 'warning')
            return redirect(url_for('approval_detail', request_id=request_id))

        comment = request.form.get('approval_comment', '').strip()
        if not comment:
            flash('请填写驳回原因', 'danger')
            return redirect(url_for('approval_detail', request_id=request_id))

        req.status = 'rejected'
        req.approver = current_user.username
        req.approval_date = date.today()
        req.approval_comment = comment

        create_notification(
            None, 'approval',
            f'审批驳回：{req.title}',
            f'冰窖 {req.ice_house.code} 的申请被驳回：{comment}',
            'approval', req.id
        )

        db.session.commit()
        flash('审批已驳回', 'info')
        return redirect(url_for('approval_detail', request_id=request_id))

    # ========== 消息提醒 ==========
    @app.route('/notifications')
    @login_required
    def notifications():
        all_notifications = Notification.query.filter(
            (Notification.user_id == current_user.id) | (Notification.user_id.is_(None))
        ).order_by(Notification.created_at.desc()).limit(50).all()

        unread_count = Notification.query.filter(
            ((Notification.user_id == current_user.id) | (Notification.user_id.is_(None))) &
            (Notification.is_read == False)
        ).count()

        return render_template('notifications/list.html',
                               notifications=all_notifications,
                               unread_count=unread_count)

    @app.route('/notifications/<int:notif_id>/read', methods=['POST'])
    @login_required
    def notification_read(notif_id):
        notif = Notification.query.get_or_404(notif_id)
        notif.is_read = True
        db.session.commit()
        return jsonify({'success': True})

    @app.route('/notifications/read-all', methods=['POST'])
    @login_required
    def notifications_read_all():
        Notification.query.filter(
            ((Notification.user_id == current_user.id) | (Notification.user_id.is_(None))) &
            (Notification.is_read == False)
        ).update({'is_read': True})
        db.session.commit()
        flash('全部标记已读', 'success')
        return redirect(url_for('notifications'))

    @app.context_processor
    def inject_notifications():
        if current_user.is_authenticated:
            unread_count = Notification.query.filter(
                ((Notification.user_id == current_user.id) | (Notification.user_id.is_(None))) &
                (Notification.is_read == False)
            ).count()
            return {'unread_notification_count': unread_count}
        return {}

    # ========== 趋势分析 ==========
    @app.route('/trends')
    @login_required
    def trends():
        ice_house_id = request.args.get('ice_house_id', type=int)
        batch_id = request.args.get('batch_id', type=int)
        start_date_str = request.args.get('start_date', '')
        end_date_str = request.args.get('end_date', '')

        houses = IceHouse.query.order_by(IceHouse.code).all()
        batches = []
        if ice_house_id:
            batches = IceBatch.query.filter_by(ice_house_id=ice_house_id).order_by(
                IceBatch.entry_date.desc()
            ).all()

        temp_data = []
        humidity_data = []
        melt_loss_data = []
        melt_rate_data = []
        labels = []

        if ice_house_id and start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

            if batch_id:
                batch = IceBatch.query.get(batch_id)
                if batch:
                    losses = MeltLoss.query.filter_by(batch_id=batch_id).filter(
                        MeltLoss.record_date.between(start_date, end_date)
                    ).order_by(MeltLoss.record_date).all()

                    if losses:
                        labels = [l.record_date.isoformat() for l in losses]
                        melt_loss_data = [l.loss_amount for l in losses]

                        cumulative = 0
                        for loss in losses:
                            cumulative += loss.loss_amount
                            rate = round((cumulative / batch.ice_count) * 100, 2) if batch.ice_count > 0 else 0
                            melt_rate_data.append(rate)
            else:
                inspections = Inspection.query.filter_by(ice_house_id=ice_house_id).filter(
                    Inspection.inspection_date.between(start_date, end_date)
                ).order_by(Inspection.inspection_date).all()

                if inspections:
                    labels = [i.inspection_date.isoformat() for i in inspections]
                    temp_data = [i.temperature for i in inspections]
                    humidity_data = [i.humidity for i in inspections]

                house_losses = MeltLoss.query.filter_by(ice_house_id=ice_house_id).filter(
                    MeltLoss.record_date.between(start_date, end_date)
                ).order_by(MeltLoss.record_date).all()

                if house_losses and not labels:
                    labels = [l.record_date.isoformat() for l in house_losses]
                melt_loss_data = [l.loss_amount for l in house_losses]

                house_batches = IceBatch.query.filter_by(ice_house_id=ice_house_id).all()
                total_ice = sum(b.ice_count for b in house_batches)
                cumulative_loss = 0
                date_loss_map = {}
                for loss in house_losses:
                    key = loss.record_date.isoformat()
                    date_loss_map[key] = date_loss_map.get(key, 0) + loss.loss_amount

                if total_ice > 0:
                    cumulative = 0
                    for label in labels:
                        cumulative += date_loss_map.get(label, 0)
                        rate = round((cumulative / total_ice) * 100, 2)
                        melt_rate_data.append(rate)

        summary = {}
        if ice_house_id and start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            total_loss = db.session.query(db.func.sum(MeltLoss.loss_amount)).filter(
                MeltLoss.ice_house_id == ice_house_id,
                MeltLoss.record_date.between(start_date, end_date)
            ).scalar() or 0

            if batch_id:
                batch = IceBatch.query.get(batch_id)
                if batch:
                    summary = {
                        'total_ice': batch.ice_count,
                        'total_loss': total_loss,
                        'melt_rate': round((total_loss / batch.ice_count) * 100, 2) if batch.ice_count > 0 else 0,
                        'remaining': batch.current_remaining
                    }
            else:
                house = IceHouse.query.get(ice_house_id)
                house_batches = IceBatch.query.filter_by(ice_house_id=ice_house_id).all()
                total_ice = sum(b.ice_count for b in house_batches)
                total_remaining = sum(b.current_remaining for b in house_batches)
                summary = {
                    'total_ice': total_ice,
                    'total_loss': total_loss,
                    'melt_rate': round((total_loss / total_ice) * 100, 2) if total_ice > 0 else 0,
                    'remaining': total_remaining
                }

        return render_template('trends/index.html',
                               houses=houses,
                               batches=batches,
                               ice_house_id=ice_house_id,
                               batch_id=batch_id,
                               start_date=start_date_str,
                               end_date=end_date_str,
                               labels=labels,
                               temp_data=temp_data,
                               humidity_data=humidity_data,
                               melt_loss_data=melt_loss_data,
                               melt_rate_data=melt_rate_data,
                               summary=summary)

    # ========== 导出报表 ==========
    @app.route('/export')
    @login_required
    def export_page():
        houses = IceHouse.query.order_by(IceHouse.code).all()
        return render_template('export/index.html', houses=houses)

    @app.route('/export/data', methods=['POST'])
    @login_required
    def export_data():
        export_type = request.form.get('export_type', 'inspections')
        ice_house_id = request.form.get('ice_house_id', type=int)
        start_date_str = request.form.get('start_date', '')
        end_date_str = request.form.get('end_date', '')

        import csv
        from io import StringIO
        from flask import Response

        start_date = None
        end_date = None
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

        output = StringIO()
        writer = csv.writer(output)

        if export_type == 'inspections':
            query = Inspection.query
            if ice_house_id:
                query = query.filter_by(ice_house_id=ice_house_id)
            if start_date:
                query = query.filter(Inspection.inspection_date >= start_date)
            if end_date:
                query = query.filter(Inspection.inspection_date <= end_date)
            records = query.order_by(Inspection.inspection_date).all()

            writer.writerow(['冰窖编号', '巡检日期', '温度(℃)', '湿度(%)', '是否渗水', '融损程度', '建议'])
            for r in records:
                writer.writerow([
                    r.ice_house.code,
                    r.inspection_date,
                    r.temperature,
                    r.humidity,
                    '是' if r.seepage else '否',
                    r.melt_level,
                    r.suggestions or ''
                ])
            filename = f'inspections_{date.today()}.csv'

        elif export_type == 'melt_losses':
            query = MeltLoss.query
            if ice_house_id:
                query = query.filter_by(ice_house_id=ice_house_id)
            if start_date:
                query = query.filter(MeltLoss.record_date >= start_date)
            if end_date:
                query = query.filter(MeltLoss.record_date <= end_date)
            records = query.order_by(MeltLoss.record_date).all()

            writer.writerow(['冰窖编号', '批次ID', '记录日期', '融损数量', '原因'])
            for r in records:
                writer.writerow([
                    r.ice_house.code,
                    r.batch_id,
                    r.record_date,
                    r.loss_amount,
                    r.reason or ''
                ])
            filename = f'melt_losses_{date.today()}.csv'

        elif export_type == 'rectifications':
            query = RectificationTask.query
            if ice_house_id:
                query = query.filter_by(ice_house_id=ice_house_id)
            if start_date:
                query = query.filter(db.func.date(RectificationTask.created_at) >= start_date)
            if end_date:
                query = query.filter(db.func.date(RectificationTask.created_at) <= end_date)
            records = query.order_by(RectificationTask.created_at).all()

            writer.writerow(['任务编号', '冰窖编号', '标题', '状态', '截止日期', '完成日期', '整改结果'])
            for r in records:
                writer.writerow([
                    r.task_no,
                    r.ice_house.code,
                    r.title,
                    r.status,
                    r.deadline or '',
                    r.actual_finish_date or '',
                    r.rectification_result or ''
                ])
            filename = f'rectifications_{date.today()}.csv'

        elif export_type == 'risk_alerts':
            query = RiskAlert.query
            if ice_house_id:
                query = query.filter_by(ice_house_id=ice_house_id)
            if start_date:
                query = query.filter(db.func.date(RiskAlert.created_at) >= start_date)
            if end_date:
                query = query.filter(db.func.date(RiskAlert.created_at) <= end_date)
            records = query.order_by(RiskAlert.created_at).all()

            writer.writerow(['冰窖编号', '预警类型', '严重程度', '标题', '状态', '创建时间', '解除时间'])
            for r in records:
                writer.writerow([
                    r.ice_house.code,
                    r.alert_type,
                    r.severity,
                    r.title,
                    r.status,
                    r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
                    r.resolved_at.strftime('%Y-%m-%d %H:%M') if r.resolved_at else ''
                ])
            filename = f'risk_alerts_{date.today()}.csv'

        else:
            flash('不支持的导出类型', 'danger')
            return redirect(url_for('export_page'))

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv; charset=utf-8-sig',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )

    def generate_transfer_no():
        prefix = 'DB' + datetime.now().strftime('%Y%m%d')
        count = TransferOrder.query.filter(
            TransferOrder.transfer_no.like(prefix + '%')
        ).count()
        return f'{prefix}{count + 1:03d}'

    def generate_outbound_no():
        prefix = 'CK' + datetime.now().strftime('%Y%m%d')
        count = OutboundRecord.query.filter(
            OutboundRecord.outbound_no.like(prefix + '%')
        ).count()
        return f'{prefix}{count + 1:03d}'

    def create_inventory_flow(ice_house_id, batch_id, flow_type, quantity,
                              balance_after, related_type=None, related_id=None,
                              operator=None, remark=None):
        flow = InventoryFlow(
            ice_house_id=ice_house_id,
            batch_id=batch_id,
            flow_type=flow_type,
            quantity=quantity,
            balance_after=balance_after,
            related_type=related_type,
            related_id=related_id,
            operator=operator or current_user.username,
            remark=remark
        )
        db.session.add(flow)
        return flow

    # ========== 调拨管理 ==========
    @app.route('/transfers')
    @login_required
    def transfers():
        status = request.args.get('status', '')
        query = TransferOrder.query
        if status:
            query = query.filter_by(status=status)
        orders = query.order_by(TransferOrder.created_at.desc()).all()
        return render_template('transfers/list.html', orders=orders, status=status)

    @app.route('/transfers/new', methods=['GET', 'POST'])
    @login_required
    def transfer_new():
        houses = IceHouse.query.order_by(IceHouse.code).all()

        if request.method == 'POST':
            from_house_id = request.form.get('from_house_id', type=int)
            to_house_id = request.form.get('to_house_id', type=int)
            reason = request.form.get('reason', '').strip()
            applicant = request.form.get('applicant', '').strip()
            batch_ids = request.form.getlist('batch_ids[]', type=int)
            quantities = request.form.getlist('quantities[]', type=int)

            if not from_house_id or not to_house_id:
                flash('请选择调出和调入冰窖', 'danger')
                batches_from = []
                return render_template('transfers/form.html', order=None, houses=houses,
                                       from_house_id=from_house_id, batches_from=batches_from)

            if from_house_id == to_house_id:
                flash('调出冰窖和调入冰窖不能相同', 'danger')
                batches_from = IceBatch.query.filter_by(ice_house_id=from_house_id).filter(
                    IceBatch.current_remaining > 0
                ).order_by(IceBatch.entry_date.desc()).all()
                return render_template('transfers/form.html', order=None, houses=houses,
                                       from_house_id=from_house_id, batches_from=batches_from)

            if not batch_ids or not quantities:
                flash('请至少添加一条调拨明细', 'danger')
                batches_from = IceBatch.query.filter_by(ice_house_id=from_house_id).filter(
                    IceBatch.current_remaining > 0
                ).order_by(IceBatch.entry_date.desc()).all()
                return render_template('transfers/form.html', order=None, houses=houses,
                                       from_house_id=from_house_id, batches_from=batches_from)

            batch_quantity_map = {}
            for i, bid in enumerate(batch_ids):
                if i < len(quantities) and quantities[i] > 0:
                    batch_quantity_map[bid] = quantities[i]

            if not batch_quantity_map:
                flash('请填写有效的调拨数量', 'danger')
                batches_from = IceBatch.query.filter_by(ice_house_id=from_house_id).filter(
                    IceBatch.current_remaining > 0
                ).order_by(IceBatch.entry_date.desc()).all()
                return render_template('transfers/form.html', order=None, houses=houses,
                                       from_house_id=from_house_id, batches_from=batches_from)

            for bid, qty in batch_quantity_map.items():
                batch = IceBatch.query.get(bid)
                if not batch or batch.ice_house_id != from_house_id:
                    flash(f'批次 {bid} 不存在或不属于调出冰窖', 'danger')
                    batches_from = IceBatch.query.filter_by(ice_house_id=from_house_id).filter(
                        IceBatch.current_remaining > 0
                    ).order_by(IceBatch.entry_date.desc()).all()
                    return render_template('transfers/form.html', order=None, houses=houses,
                                           from_house_id=from_house_id, batches_from=batches_from)
                if qty > batch.current_remaining:
                    flash(f'批次 {bid} 调拨数量不能大于当前剩余量（{batch.current_remaining}）', 'danger')
                    batches_from = IceBatch.query.filter_by(ice_house_id=from_house_id).filter(
                        IceBatch.current_remaining > 0
                    ).order_by(IceBatch.entry_date.desc()).all()
                    return render_template('transfers/form.html', order=None, houses=houses,
                                           from_house_id=from_house_id, batches_from=batches_from)

            order = TransferOrder(
                transfer_no=generate_transfer_no(),
                from_house_id=from_house_id,
                to_house_id=to_house_id,
                reason=reason,
                applicant=applicant or current_user.username,
                apply_date=date.today(),
                status='pending',
                created_by=current_user.id
            )
            db.session.add(order)
            db.session.flush()

            for bid, qty in batch_quantity_map.items():
                item = TransferItem(
                    transfer_order_id=order.id,
                    batch_id=bid,
                    quantity=qty
                )
                db.session.add(item)

            admin = User.query.filter_by(username='admin').first()
            if admin:
                create_notification(
                    admin.id, 'transfer',
                    f'新调拨申请：{order.transfer_no}',
                    f'{order.from_house.code} → {order.to_house.code}，共{order.total_quantity()}块冰待审批',
                    'transfer', order.id
                )

            db.session.commit()
            flash('调拨申请已提交，等待审批', 'success')
            return redirect(url_for('transfer_detail', order_id=order.id))

        batches_from = []
        return render_template('transfers/form.html', order=None, houses=houses,
                               from_house_id=None, batches_from=batches_from)

    @app.route('/transfers/<int:order_id>')
    @login_required
    def transfer_detail(order_id):
        order = TransferOrder.query.get_or_404(order_id)
        return render_template('transfers/detail.html', order=order)

    @app.route('/transfers/<int:order_id>/approve', methods=['POST'])
    @login_required
    def transfer_approve(order_id):
        order = TransferOrder.query.get_or_404(order_id)
        if order.status != 'pending':
            flash('该调拨单已处理', 'warning')
            return redirect(url_for('transfer_detail', order_id=order_id))

        comment = request.form.get('approval_comment', '').strip()

        for item in order.items:
            batch = item.batch
            if item.quantity > batch.current_remaining:
                flash(f'审批失败：批次 {batch.id} 库存不足，当前剩余 {batch.current_remaining}', 'danger')
                return redirect(url_for('transfer_detail', order_id=order_id))

        order.status = 'approved'
        order.approver = current_user.username
        order.approval_date = date.today()
        order.approval_comment = comment

        create_notification(
            None, 'transfer',
            f'调拨已审批通过：{order.transfer_no}',
            f'{order.from_house.code} → {order.to_house.code}，共{order.total_quantity()}块冰',
            'transfer', order.id
        )

        db.session.commit()
        flash('调拨审批通过', 'success')
        return redirect(url_for('transfer_detail', order_id=order_id))

    @app.route('/transfers/<int:order_id>/reject', methods=['POST'])
    @login_required
    def transfer_reject(order_id):
        order = TransferOrder.query.get_or_404(order_id)
        if order.status != 'pending':
            flash('该调拨单已处理', 'warning')
            return redirect(url_for('transfer_detail', order_id=order_id))

        comment = request.form.get('approval_comment', '').strip()
        if not comment:
            flash('请填写驳回原因', 'danger')
            return redirect(url_for('transfer_detail', order_id=order_id))

        order.status = 'rejected'
        order.approver = current_user.username
        order.approval_date = date.today()
        order.approval_comment = comment

        create_notification(
            None, 'transfer',
            f'调拨已被驳回：{order.transfer_no}',
            f'驳回原因：{comment}',
            'transfer', order.id
        )

        db.session.commit()
        flash('调拨已驳回', 'info')
        return redirect(url_for('transfer_detail', order_id=order_id))

    @app.route('/transfers/<int:order_id>/execute', methods=['POST'])
    @login_required
    def transfer_execute(order_id):
        order = TransferOrder.query.get_or_404(order_id)
        if order.status != 'approved':
            flash('只有审批通过的调拨单才能执行出库', 'danger')
            return redirect(url_for('transfer_detail', order_id=order_id))

        executor = request.form.get('executor', '').strip() or current_user.username

        for item in order.items:
            batch = item.batch
            if item.quantity > batch.current_remaining:
                flash(f'执行失败：批次 {batch.id} 库存不足，当前剩余 {batch.current_remaining}', 'danger')
                return redirect(url_for('transfer_detail', order_id=order_id))

        for item in order.items:
            batch = item.batch
            batch.current_remaining -= item.quantity
            create_inventory_flow(
                ice_house_id=order.from_house_id,
                batch_id=batch.id,
                flow_type='transfer_out',
                quantity=-item.quantity,
                balance_after=batch.current_remaining,
                related_type='transfer',
                related_id=order.id,
                operator=executor,
                remark=f'调拨至 {order.to_house.code}'
            )

        order.status = 'executing'
        order.executor = executor
        order.execute_date = date.today()

        create_notification(
            None, 'transfer',
            f'调拨已出库：{order.transfer_no}',
            f'{order.from_house.code} → {order.to_house.code}，已出库{order.total_quantity()}块冰，待接收确认',
            'transfer', order.id
        )

        db.session.commit()
        flash('调拨出库执行成功，待接收确认', 'success')
        return redirect(url_for('transfer_detail', order_id=order_id))

    @app.route('/transfers/<int:order_id>/receive', methods=['GET', 'POST'])
    @login_required
    def transfer_receive(order_id):
        order = TransferOrder.query.get_or_404(order_id)
        if order.status != 'executing':
            flash('只有执行中的调拨单才能进行接收确认', 'danger')
            return redirect(url_for('transfer_detail', order_id=order_id))

        if request.method == 'POST':
            receiver = request.form.get('receiver', '').strip() or current_user.username
            receive_remark = request.form.get('receive_remark', '').strip()
            received_qtys = request.form.getlist('received_quantities[]', type=int)

            for i, item in enumerate(order.items):
                received = received_qtys[i] if i < len(received_qtys) else item.quantity
                if received < 0:
                    flash('实收数量不能为负数', 'danger')
                    return render_template('transfers/receive.html', order=order)
                if received > item.quantity:
                    flash('实收数量不能大于调拨数量', 'danger')
                    return render_template('transfers/receive.html', order=order)
                item.received_quantity = received

                target_batch = IceBatch.query.filter_by(
                    ice_house_id=order.to_house_id,
                    entry_date=item.batch.entry_date,
                    ice_count=item.batch.ice_count
                ).first()

                if target_batch:
                    target_batch.current_remaining += received
                else:
                    target_batch = IceBatch(
                        ice_house_id=order.to_house_id,
                        entry_date=item.batch.entry_date,
                        ice_count=item.batch.ice_count,
                        expected_storage_period=item.batch.expected_storage_period,
                        current_remaining=received
                    )
                    db.session.add(target_batch)
                    db.session.flush()

                create_inventory_flow(
                    ice_house_id=order.to_house_id,
                    batch_id=target_batch.id,
                    flow_type='transfer_in',
                    quantity=received,
                    balance_after=target_batch.current_remaining,
                    related_type='transfer',
                    related_id=order.id,
                    operator=receiver,
                    remark=f'从 {order.from_house.code} 调入'
                )

                loss_qty = item.quantity - received
                if loss_qty > 0:
                    create_inventory_flow(
                        ice_house_id=order.to_house_id,
                        batch_id=target_batch.id,
                        flow_type='melt_loss',
                        quantity=-loss_qty,
                        balance_after=target_batch.current_remaining,
                        related_type='transfer',
                        related_id=order.id,
                        operator=receiver,
                        remark='调拨途中损耗'
                    )

            order.status = 'completed'
            order.receiver = receiver
            order.receive_date = date.today()
            order.receive_remark = receive_remark

            create_notification(
                None, 'transfer',
                f'调拨已完成：{order.transfer_no}',
                f'实收{order.total_received()}块冰，接收人：{receiver}',
                'transfer', order.id
            )

            db.session.commit()
            flash('接收确认完成，调拨已完成', 'success')
            return redirect(url_for('transfer_detail', order_id=order_id))

        return render_template('transfers/receive.html', order=order)

    # ========== 出窖登记 ==========
    @app.route('/outbounds')
    @login_required
    def outbounds():
        ice_house_id = request.args.get('ice_house_id', type=int)
        purpose = request.args.get('purpose', '')

        query = OutboundRecord.query
        if ice_house_id:
            query = query.filter_by(ice_house_id=ice_house_id)
        if purpose:
            query = query.filter_by(purpose=purpose)

        records = query.order_by(OutboundRecord.outbound_date.desc()).all()
        houses = IceHouse.query.order_by(IceHouse.code).all()

        purposes = ['食品保鲜', '医疗冷链', '工业冷却', '其他']
        return render_template('outbounds/list.html', records=records, houses=houses,
                               ice_house_id=ice_house_id, purpose=purpose, purposes=purposes)

    @app.route('/outbounds/new', methods=['GET', 'POST'])
    @login_required
    def outbound_new():
        houses = IceHouse.query.order_by(IceHouse.code).all()
        purposes = ['食品保鲜', '医疗冷链', '工业冷却', '其他']

        if request.method == 'POST':
            ice_house_id = request.form.get('ice_house_id', type=int)
            batch_id = request.form.get('batch_id', type=int)
            quantity = request.form.get('quantity', type=int)
            purpose = request.form.get('purpose', '').strip()
            destination = request.form.get('destination', '').strip()
            handler = request.form.get('handler', '').strip()
            outbound_date_str = request.form.get('outbound_date')
            remark = request.form.get('remark', '').strip()

            if not ice_house_id or not batch_id or not quantity or not purpose:
                flash('请填写必填信息', 'danger')
                batches = IceBatch.query.filter_by(ice_house_id=ice_house_id or 0).filter(
                    IceBatch.current_remaining > 0
                ).order_by(IceBatch.entry_date.desc()).all()
                return render_template('outbounds/form.html', record=None, houses=houses,
                                       purposes=purposes, batches=batches, ice_house_id=ice_house_id)

            batch = IceBatch.query.get(batch_id)
            if not batch or batch.ice_house_id != ice_house_id:
                flash('批次不存在或不属于所选冰窖', 'danger')
                batches = IceBatch.query.filter_by(ice_house_id=ice_house_id).filter(
                    IceBatch.current_remaining > 0
                ).order_by(IceBatch.entry_date.desc()).all()
                return render_template('outbounds/form.html', record=None, houses=houses,
                                       purposes=purposes, batches=batches, ice_house_id=ice_house_id)

            if quantity > batch.current_remaining:
                flash('出窖数量不能大于当前剩余量', 'danger')
                batches = IceBatch.query.filter_by(ice_house_id=ice_house_id).filter(
                    IceBatch.current_remaining > 0
                ).order_by(IceBatch.entry_date.desc()).all()
                return render_template('outbounds/form.html', record=None, houses=houses,
                                       purposes=purposes, batches=batches, ice_house_id=ice_house_id)

            outbound_date = date.today()
            if outbound_date_str:
                outbound_date = datetime.strptime(outbound_date_str, '%Y-%m-%d').date()
                if outbound_date > date.today():
                    flash('出窖日期不能晚于当前日期', 'danger')
                    batches = IceBatch.query.filter_by(ice_house_id=ice_house_id).filter(
                        IceBatch.current_remaining > 0
                    ).order_by(IceBatch.entry_date.desc()).all()
                    return render_template('outbounds/form.html', record=None, houses=houses,
                                           purposes=purposes, batches=batches, ice_house_id=ice_house_id)

            record = OutboundRecord(
                outbound_no=generate_outbound_no(),
                ice_house_id=ice_house_id,
                batch_id=batch_id,
                quantity=quantity,
                purpose=purpose,
                destination=destination,
                handler=handler or current_user.username,
                outbound_date=outbound_date,
                remark=remark,
                created_by=current_user.id
            )
            db.session.add(record)
            db.session.flush()

            batch.current_remaining -= quantity
            create_inventory_flow(
                ice_house_id=ice_house_id,
                batch_id=batch_id,
                flow_type='outbound',
                quantity=-quantity,
                balance_after=batch.current_remaining,
                related_type='outbound',
                related_id=record.id,
                operator=handler or current_user.username,
                remark=f'{purpose} - {destination}' if destination else purpose
            )

            db.session.commit()
            flash('出窖登记成功', 'success')
            return redirect(url_for('outbounds'))

        batches = []
        return render_template('outbounds/form.html', record=None, houses=houses,
                               purposes=purposes, batches=batches, ice_house_id=None)

    @app.route('/outbounds/<int:record_id>')
    @login_required
    def outbound_detail(record_id):
        record = OutboundRecord.query.get_or_404(record_id)
        return render_template('outbounds/detail_modal.html', record=record)

    # ========== 库存流水 ==========
    @app.route('/inventory-flows')
    @login_required
    def inventory_flows():
        ice_house_id = request.args.get('ice_house_id', type=int)
        batch_id = request.args.get('batch_id', type=int)
        flow_type = request.args.get('flow_type', '')
        start_date_str = request.args.get('start_date', '')
        end_date_str = request.args.get('end_date', '')

        query = InventoryFlow.query
        if ice_house_id:
            query = query.filter_by(ice_house_id=ice_house_id)
        if batch_id:
            query = query.filter_by(batch_id=batch_id)
        if flow_type:
            query = query.filter_by(flow_type=flow_type)
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            query = query.filter(InventoryFlow.operation_time >= start_date)
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query = query.filter(InventoryFlow.operation_time <= end_date)

        flows = query.order_by(InventoryFlow.operation_time.desc()).all()
        houses = IceHouse.query.order_by(IceHouse.code).all()
        batches = []
        if ice_house_id:
            batches = IceBatch.query.filter_by(ice_house_id=ice_house_id).order_by(
                IceBatch.entry_date.desc()
            ).all()

        flow_types = [
            ('entry', '入窖'),
            ('transfer_out', '调拨出库'),
            ('transfer_in', '调拨入库'),
            ('outbound', '出窖'),
            ('melt_loss', '融损'),
            ('adjust', '库存调整'),
        ]

        return render_template('inventory_flows/list.html',
                               flows=flows, houses=houses, batches=batches,
                               ice_house_id=ice_house_id, batch_id=batch_id,
                               flow_type=flow_type, flow_types=flow_types,
                               start_date=start_date_str, end_date=end_date_str)

    # ========== 批次追溯链路 ==========
    @app.route('/batch-trace/<int:batch_id>')
    @login_required
    def batch_trace(batch_id):
        batch = IceBatch.query.get_or_404(batch_id)

        flows = InventoryFlow.query.filter_by(batch_id=batch_id).order_by(
            InventoryFlow.operation_time.asc()
        ).all()

        transfer_items_out = TransferItem.query.filter_by(batch_id=batch_id).all()
        transfer_ids_out = [item.transfer_order_id for item in transfer_items_out]
        transfers_out = TransferOrder.query.filter(
            TransferOrder.id.in_(transfer_ids_out)
        ).order_by(TransferOrder.created_at.desc()).all() if transfer_ids_out else []

        trace_chain = []
        trace_chain.append({
            'type': 'origin',
            'title': '入窖',
            'house': batch.ice_house.code,
            'date': batch.entry_date,
            'quantity': batch.ice_count,
            'description': f'初始入窖 {batch.ice_count} 块'
        })

        for flow in flows:
            if flow.flow_type == 'transfer_out':
                order = TransferOrder.query.filter_by(id=flow.related_id).first() if flow.related_type == 'transfer' else None
                trace_chain.append({
                    'type': 'transfer_out',
                    'title': '调拨出库',
                    'house': order.to_house.code if order else '',
                    'date': flow.operation_time.date() if flow.operation_time else '',
                    'quantity': abs(flow.quantity),
                    'description': flow.remark or '',
                    'order_no': order.transfer_no if order else ''
                })
            elif flow.flow_type == 'transfer_in':
                order = TransferOrder.query.filter_by(id=flow.related_id).first() if flow.related_type == 'transfer' else None
                trace_chain.append({
                    'type': 'transfer_in',
                    'title': '调拨入库',
                    'house': order.from_house.code if order else '',
                    'date': flow.operation_time.date() if flow.operation_time else '',
                    'quantity': abs(flow.quantity),
                    'description': flow.remark or '',
                    'order_no': order.transfer_no if order else ''
                })
            elif flow.flow_type == 'outbound':
                record = OutboundRecord.query.filter_by(id=flow.related_id).first() if flow.related_type == 'outbound' else None
                trace_chain.append({
                    'type': 'outbound',
                    'title': '出窖',
                    'house': '',
                    'date': flow.operation_time.date() if flow.operation_time else '',
                    'quantity': abs(flow.quantity),
                    'description': flow.remark or '',
                    'purpose': record.purpose if record else '',
                    'destination': record.destination if record else ''
                })
            elif flow.flow_type == 'melt_loss':
                trace_chain.append({
                    'type': 'melt_loss',
                    'title': '融损',
                    'house': '',
                    'date': flow.operation_time.date() if flow.operation_time else '',
                    'quantity': abs(flow.quantity),
                    'description': flow.remark or ''
                })

        return render_template('batch_trace/detail.html',
                               batch=batch, flows=flows, trace_chain=trace_chain,
                               transfers_out=transfers_out)

    # ========== 异常损耗比对 ==========
    @app.route('/loss-comparison')
    @login_required
    def loss_comparison():
        ice_house_id = request.args.get('ice_house_id', type=int)
        start_date_str = request.args.get('start_date', '')
        end_date_str = request.args.get('end_date', '')

        houses = IceHouse.query.order_by(IceHouse.code).all()
        results = []

        if ice_house_id and start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

            batches = IceBatch.query.filter_by(ice_house_id=ice_house_id).all()

            for batch in batches:
                melt_losses = MeltLoss.query.filter_by(batch_id=batch.id).filter(
                    MeltLoss.record_date.between(start_date, end_date)
                ).all()
                total_melt_loss = sum(l.loss_amount for l in melt_losses)

                transfer_loss_qty = 0
                transfer_items = TransferItem.query.filter_by(batch_id=batch.id).all()
                for item in transfer_items:
                    order = TransferOrder.query.get(item.transfer_order_id)
                    if order and order.status == 'completed' and order.receive_date:
                        if start_date <= order.receive_date <= end_date:
                            transfer_loss_qty += (item.quantity - item.received_quantity)

                outbound_flows = InventoryFlow.query.filter_by(
                    batch_id=batch.id, flow_type='outbound'
                ).all()

                total_out = sum(abs(f.quantity) for f in outbound_flows)
                total_loss = total_melt_loss + transfer_loss_qty

                expected_loss = 0
                storage_days = (date.today() - batch.entry_date).days
                if storage_days > 0 and batch.ice_count > 0:
                    daily_rate = 0.002
                    expected_loss = int(batch.ice_count * daily_rate * min(storage_days, 365))

                abnormal = total_loss > expected_loss * 1.3
                diff = total_loss - expected_loss
                diff_rate = round((diff / expected_loss * 100), 2) if expected_loss > 0 else 0

                results.append({
                    'batch_id': batch.id,
                    'entry_date': batch.entry_date,
                    'ice_count': batch.ice_count,
                    'current_remaining': batch.current_remaining,
                    'melt_loss': total_melt_loss,
                    'transfer_loss': transfer_loss_qty,
                    'total_loss': total_loss,
                    'expected_loss': expected_loss,
                    'abnormal': abnormal,
                    'diff': diff,
                    'diff_rate': diff_rate,
                })

            results.sort(key=lambda x: x['total_loss'], reverse=True)

        return render_template('loss_comparison/index.html',
                               houses=houses, results=results,
                               ice_house_id=ice_house_id,
                               start_date=start_date_str, end_date=end_date_str)

    @app.context_processor
    def inject_now():
        return {'now': datetime.utcnow(), 'date': date}

    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5001)
