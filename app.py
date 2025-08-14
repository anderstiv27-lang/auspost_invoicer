import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, joinedload
from datetime import datetime, date
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import hashlib

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.getenv('SECRET_KEY', 'change-this-secret')
app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE='Lax')

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///auspost.db')
engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class User(Base, UserMixin):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    role = Column(String(20), default='worker')
    price_per_pkg = Column(Float, default=1.0)
    super_rate = Column(Float, default=0.115)
    entries = relationship('DailyEntry', back_populates='user')

class DailyEntry(Base):
    __tablename__ = 'entries'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    work_date = Column(Date, nullable=False)
    packages = Column(Integer, default=0)
    notes = Column(Text, default='')
    admin_comment = Column(Text, default='')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    user = relationship('User', back_populates='entries', lazy='joined')  # eager

Base.metadata.create_all(engine)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    db = SessionLocal()
    u = db.get(User, int(user_id))
    db.close()
    return u

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode('utf-8')).hexdigest()

def ensure_default_admin():
    db = SessionLocal()
    if not db.query(User).filter_by(role='admin').first():
        admin = User(name='Admin', email='admin@example.com', password_hash=hash_pw('admin123'), role='admin', price_per_pkg=1.5, super_rate=0.115)
        db.add(admin); db.commit()
    db.close()
ensure_default_admin()

def compute_invoice(packages_sum: int, price_per_pkg: float, super_rate: float, gst_rate: float=0.10, van_rent: float=100.0):
    base = packages_sum * price_per_pkg
    super_amount = base * super_rate
    subtotal = base + super_amount
    gst = subtotal * gst_rate
    total_with_gst = subtotal + gst
    final_total = total_with_gst - van_rent
    return {
        'packages': packages_sum,
        'price_per_pkg': price_per_pkg,
        'super_rate': super_rate,
        'base': round(base, 2),
        'super_amount': round(super_amount, 2),
        'subtotal': round(subtotal, 2),
        'gst_rate': gst_rate,
        'gst': round(gst, 2),
        'van_rent': round(van_rent, 2),
        'total': round(final_total, 2)
    }

@app.route('/')
@login_required
def home():
    db = SessionLocal()
    if current_user.role == 'admin':
        items = db.query(DailyEntry).order_by(DailyEntry.work_date.desc(), DailyEntry.id.desc()).limit(50).all()
        users = db.query(User).order_by(User.name).all()
        db.close()
        return render_template('admin_dashboard.html', items=items, users=users)
    else:
        items = db.query(DailyEntry).filter_by(user_id=current_user.id).order_by(DailyEntry.work_date.desc()).all()
        db.close()
        return render_template('worker_dashboard.html', items=items)

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email','').strip().lower()
        pw = request.form.get('password','')
        db = SessionLocal()
        user = db.query(User).filter_by(email=email).first()
        if user and user.password_hash == hash_pw(pw):
            login_user(user)
            db.close()
            return redirect(url_for('home'))
        db.close()
        flash('Email o contraseña incorrectos.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/entry/new', methods=['GET','POST'])
@login_required
def entry_new():
    if request.method == 'POST':
        work_date = request.form.get('work_date')
        packages = int(request.form.get('packages') or 0)
        notes = request.form.get('notes','')
        db = SessionLocal()
        e = DailyEntry(user_id=current_user.id, work_date=datetime.strptime(work_date, '%Y-%m-%d').date(), packages=packages, notes=notes)
        db.add(e); db.commit(); db.close()
        flash('Registro guardado.')
        return redirect(url_for('home'))
    today = date.today().strftime('%Y-%m-%d')
    return render_template('entry_form.html', entry=None, today=today)

@app.route('/entry/<int:entry_id>/edit', methods=['GET','POST'])
@login_required
def entry_edit(entry_id):
    db = SessionLocal()
    e = db.get(DailyEntry, entry_id)
    if not e or (current_user.role != 'admin' and e.user_id != current_user.id):
        db.close(); return 'No autorizado', 403
    if request.method == 'POST':
        e.work_date = datetime.strptime(request.form.get('work_date'), '%Y-%m-%d').date()
        e.packages = int(request.form.get('packages') or 0)
        e.notes = request.form.get('notes','')
        e.updated_at = datetime.utcnow()
        db.commit(); db.close()
        flash('Registro actualizado.')
        return redirect(url_for('home'))
    today = e.work_date.strftime('%Y-%m-%d')
    out = render_template('entry_form.html', entry=e, today=today)
    db.close()
    return out

@app.route('/admin/users', methods=['GET','POST'])
@login_required
def admin_users():
    if current_user.role != 'admin':
        return 'No autorizado', 403
    db = SessionLocal()
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        email = request.form.get('email','').strip().lower()
        pw = request.form.get('password','').strip()
        price = float(request.form.get('price_per_pkg') or 0)
        super_rate = float(request.form.get('super_rate') or 0)
        role = request.form.get('role','worker')
        if not name or not email or not pw:
            flash('Completa nombre, email y contraseña.')
        elif db.query(User).filter_by(email=email).first():
            flash('Ese email ya existe.')
        else:
            u = User(name=name, email=email, password_hash=hash_pw(pw), role=role, price_per_pkg=price, super_rate=super_rate)
            db.add(u); db.commit()
            flash('Usuario creado.')
    users = db.query(User).order_by(User.name).all()
    db.close()
    return render_template('admin_users.html', users=users)

@app.route('/admin/entry/<int:entry_id>/comment', methods=['POST'])
@login_required
def admin_comment(entry_id):
    if current_user.role != 'admin':
        return 'No autorizado', 403
    db = SessionLocal()
    e = db.get(DailyEntry, entry_id)
    if not e:
        db.close(); return 'No encontrado', 404
    e.admin_comment = request.form.get('admin_comment','')
    db.commit(); db.close()
    flash('Comentario guardado.')
    return redirect(url_for('home'))

@app.route('/invoice', methods=['GET','POST'])
@login_required
def invoice():
    db = SessionLocal()
    users = db.query(User).order_by(User.name).all()
    result = None
    selected_user_id = None
    if request.method == 'POST':
        selected_user_id = int(request.form.get('user_id'))
        start = datetime.strptime(request.form.get('start'), '%Y-%m-%d').date()
        end = datetime.strptime(request.form.get('end'), '%Y-%m-%d').date()
        van_rent = float(request.form.get('van_rent') or 100.0)
        gst_rate = 0.10
        u = db.get(User, selected_user_id)
        total_packages = db.query(func.sum(DailyEntry.packages)).filter(
            DailyEntry.user_id==selected_user_id,
            DailyEntry.work_date>=start,
            DailyEntry.work_date<=end
        ).scalar() or 0
        calc = compute_invoice(total_packages, u.price_per_pkg, u.super_rate, gst_rate, van_rent)
        result = {'user': u, 'start': start, 'end': end, 'calc': calc}
    db.close()
    return render_template('invoice.html', users=users, result=result, selected_user_id=selected_user_id)

@app.route('/invoice/pdf')
@login_required
def invoice_pdf():
    user_id = int(request.args.get('user_id'))
    start = datetime.strptime(request.args.get('start'), '%Y-%m-%d').date()
    end = datetime.strptime(request.args.get('end'), '%Y-%m-%d').date()
    van_rent = float(request.args.get('van_rent') or 100.0)

    db = SessionLocal()
    u = db.get(User, user_id)
    total_packages = db.query(func.sum(DailyEntry.packages)).filter(
        DailyEntry.user_id==user_id,
        DailyEntry.work_date>=start,
        DailyEntry.work_date<=end
    ).scalar() or 0
    calc = compute_invoice(total_packages, u.price_per_pkg, u.super_rate, 0.10, van_rent)
    db.close()

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    x, y = 40, H - 60

    def line(txt, size=11, bold=False, dy=18):
        nonlocal y
        c.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
        c.drawString(x, y, txt)
        y -= dy

    line("INVOICE - Australia Post Contractor", 14, True, 24)
    line(f"Contractor: {u.name} ({u.email})")
    line(f"Period: {start} to {end}", 11, False, 24)
    line("Breakdown:", 12, True, 18)
    lines = [
        f"Total packages: {calc['packages']}",
        f"Price per package: ${calc['price_per_pkg']:.2f}",
        f"Base (packages * price): ${calc['base']:.2f}",
        f"Super rate: {calc['super_rate']*100:.2f}%",
        f"Super amount: ${calc['super_amount']:.2f}",
        f"Subtotal (base + super): ${calc['subtotal']:.2f}",
        f"GST {int(calc['gst_rate']*100)}%: ${calc['gst']:.2f}",
        f"Total + GST: {(calc['subtotal'] + calc['gst']):.2f}",
        f"Van rent deduction: -${calc['van_rent']:.2f}",
        f"FINAL TOTAL: ${calc['total']:.2f}",
    ]
    for ln in lines:
        line(ln)

    c.showPage(); c.save()
    buf.seek(0)
    filename = f"invoice_{u.name.replace(' ','_')}_{start}_{end}.pdf"
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=filename)

@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False)
