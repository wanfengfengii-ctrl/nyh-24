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

from models import db, User, IceHouse, IceBatch, Inspection, MeltLoss, Repair


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

        recent_inspections = Inspection.query.order_by(
            Inspection.inspection_date.desc()
        ).limit(5).all()

        recent_repairs = Repair.query.order_by(
            Repair.report_date.desc()
        ).limit(5).all()

        return render_template('index.html',
                               total_houses=total_houses,
                               open_houses=open_houses,
                               high_risk_houses=high_risk_houses,
                               total_batches=total_batches,
                               total_inspections=total_inspections,
                               pending_repairs=pending_repairs,
                               recent_inspections=recent_inspections,
                               recent_repairs=recent_repairs)

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

            if is_open and house.has_unfinished_repairs():
                flash('存在未完成修缮的冰窖不能设置为开放状态', 'danger')
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
            house.update_risk_status()

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
            house.update_risk_status()

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

    @app.context_processor
    def inject_now():
        return {'now': datetime.utcnow()}

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
