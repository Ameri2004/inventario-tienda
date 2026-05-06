from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)

# --- CONFIGURACIÓN DE SEGURIDAD Y SESIÓN ---
app.secret_key = 'clave_uab_sistemas_2026' # Clave para cifrar las sesiones
app.config.update(
    SESSION_COOKIE_SECURE=True,    # Obligatorio para HTTPS (Render usa SSL)
    SESSION_COOKIE_SAMESITE='Lax', # Evita que el navegador bloquee la cookie de sesión
)

# --- CONFIGURACIÓN DE BASE DE DATOS ---
uri = os.environ.get('DATABASE_URL', 'postgresql://postgres:orly123@localhost:5432/tienda_uab_v3')

# Corrección para compatibilidad de SQLAlchemy con Render/Heroku
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ─────────────────────────────────────────
#  MODELOS DE BASE DE DATOS
# ─────────────────────────────────────────

class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)

class Producto(db.Model):
    __tablename__ = 'productos'
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    precio_docena = db.Column(db.Numeric(10, 2), nullable=False) 
    stock_unidades = db.Column(db.Integer, default=0)

class Venta(db.Model):
    __tablename__ = 'ventas'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.now)
    producto_nombre = db.Column(db.String(150), nullable=False)
    total = db.Column(db.Numeric(10, 2), nullable=False)
    cliente_nombre = db.Column(db.String(150))

# --- INICIALIZACIÓN CON LOGS DETALLADOS ---
with app.app_context():
    db.create_all()
    # Verifica el usuario que tú definiste (IverPerez)
    admin_check = Usuario.query.filter_by(username='IverPerez').first()
    if not admin_check:
        db.session.add(Usuario(username='IverPerez', password='123456789'))
        db.session.commit()
        print(">>> [DB] Usuario IverPerez creado por primera vez.")
    else:
        print(f">>> [DB] El usuario {admin_check.username} ya existe en la base de datos.")

# ─────────────────────────────────────────
#  RUTAS DE ACCESO (LOGIN MEJORADO)
# ─────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username')
        p = request.form.get('password')
        
        # Buscamos al usuario en la base de datos
        user = Usuario.query.filter_by(username=u).first()
        
        if user and user.password == p:
            session.permanent = True # La sesión no se borra al cerrar el navegador
            session['user_id'] = user.id
            session['username'] = user.username
            print(f">>> [LOGIN SUCCESS] Acceso concedido a: {u}")
            return redirect(url_for('index'))
        else:
            print(f">>> [LOGIN FAILED] Intento fallido con usuario: {u}")
            flash('Usuario o contraseña incorrectos', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ─────────────────────────────────────────
#  RUTAS PRINCIPALES (PROTEGIDAS)
# ─────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' not in session:
        print(">>> [AUTH] Intento de acceso sin sesión activa. Redirigiendo al Login.")
        return redirect(url_for('login'))
    
    productos = Producto.query.order_by(Producto.nombre).all()
    ventas = Venta.query.order_by(Venta.id.desc()).all()
    gran_total = sum(float(v.total) for v in ventas)
    
    return render_template('index.html', productos=productos, ventas=ventas, gran_total=gran_total)

@app.route('/registrar', methods=['POST'])
def registrar():
    if 'user_id' not in session: return redirect(url_for('login'))
    try:
        nuevo = Producto(
            codigo=request.form.get('codigo'),
            nombre=request.form.get('nombre'),
            precio_docena=float(request.form.get('precio')),
            stock_unidades=int(request.form.get('stock'))
        )
        db.session.add(nuevo)
        db.session.commit()
        flash('Producto registrado con éxito', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error: El código ya existe o datos inválidos', 'danger')
    return redirect(url_for('index'))

@app.route('/eliminar_producto/<int:id>', methods=['POST'])
def eliminar_producto(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    p = Producto.query.get_or_404(id)
    db.session.delete(p)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/imprimir/<int:venta_id>')
def imprimir(venta_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    v = Venta.query.get_or_404(venta_id)
    return render_template('factura.html', venta=v)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)