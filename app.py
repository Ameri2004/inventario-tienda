from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)

# --- CONFIGURACIÓN DE SEGURIDAD Y SESIÓN ---
app.secret_key = 'clave_uab_sistemas_2026'
app.config.update(
    SESSION_COOKIE_SECURE=True,    
    SESSION_COOKIE_SAMESITE='Lax', 
)

# --- CONFIGURACIÓN DE BASE DE DATOS (POSTGRESQL) ---
uri = os.environ.get('DATABASE_URL', 'postgresql://postgres:orly123@localhost:5432/tienda_uab_v3')
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
    cantidad = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Numeric(10, 2), nullable=False)
    cliente_nombre = db.Column(db.String(150))

# --- INICIALIZACIÓN DE LA BASE DE DATOS ---
with app.app_context():
    db.create_all()
    # Aseguramos que tu usuario IverPerez exista
    admin_check = Usuario.query.filter_by(username='IverPerez').first()
    if not admin_check:
        db.session.add(Usuario(username='IverPerez', password='123456789'))
        db.session.commit()
        print(">>> [DB] Usuario IverPerez creado.")

# ─────────────────────────────────────────
#  RUTAS DE AUTENTICACIÓN
# ─────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username')
        p = request.form.get('password')
        user = Usuario.query.filter_by(username=u, password=p).first()
        if user:
            session.permanent = True
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('index'))
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ─────────────────────────────────────────
#  RUTAS DEL SISTEMA (PRODUCTOS Y VENTAS)
# ─────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    productos = Producto.query.order_by(Producto.nombre).all()
    ventas = Venta.query.order_by(Venta.id.desc()).all()
    gran_total = sum(float(v.total) for v in ventas)
    
    return render_template('index.html', productos=productos, ventas=ventas, gran_total=gran_total)

@app.route('/registrar_producto', methods=['POST'])
def registrar_producto():
    if 'user_id' not in session: return redirect(url_for('login'))
    nuevo = Producto(
        codigo=request.form.get('codigo'),
        nombre=request.form.get('nombre'),
        precio_docena=float(request.form.get('precio')),
        stock_unidades=int(request.form.get('stock'))
    )
    db.session.add(nuevo)
    db.session.commit()
    flash('Producto registrado correctamente', 'success')
    return redirect(url_for('index'))

@app.route('/vender', methods=['POST'])
def vender():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    producto_id = request.form.get('producto_id')
    cantidad_a_vender = int(request.form.get('cantidad', 1))
    cliente = request.form.get('cliente', 'Consumidor Final')
    
    prod = Producto.query.get(producto_id)
    
    if prod and prod.stock_unidades >= cantidad_a_vender:
        # Lógica: precio por unidad = precio_docena / 12
        precio_unitario = float(prod.precio_docena) / 12
        total_venta = precio_unitario * cantidad_a_vender
        
        # 1. Descontar del stock
        prod.stock_unidades -= cantidad_a_vender
        
        # 2. Registrar la venta
        nueva_venta = Venta(
            producto_nombre=prod.nombre,
            cantidad=cantidad_a_vender,
            total=total_venta,
            cliente_nombre=cliente
        )
        
        db.session.add(nueva_venta)
        db.session.commit()
        flash(f'Venta exitosa: {prod.nombre} x{cantidad_a_vender}', 'success')
    else:
        flash('Error: Stock insuficiente para realizar la venta', 'danger')
        
    return redirect(url_for('index'))

@app.route('/eliminar_producto/<int:id>', methods=['POST'])
def eliminar_producto(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    p = Producto.query.get_or_404(id)
    db.session.delete(p)
    db.session.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)