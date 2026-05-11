from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)

# --- CONFIGURACIÓN ---
app.secret_key = 'clave_uab_sistemas_2026'
app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE='Lax')

uri = os.environ.get('DATABASE_URL', 'postgresql://postgres:orly123@localhost:5432/tienda_uab_v3')
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ─────────────────────────────────────────
#  MODELOS
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
    cliente_nombre = db.Column(db.String(150))
    total_general = db.Column(db.Numeric(10, 2), nullable=False)
    detalles = db.relationship('DetalleVenta', backref='venta_padre', lazy=True, cascade="all, delete-orphan")

class DetalleVenta(db.Model):
    __tablename__ = 'detalles_venta'
    id = db.Column(db.Integer, primary_key=True)
    venta_id = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=False)
    producto_nombre = db.Column(db.String(150), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)

# --- INICIALIZACIÓN ---
with app.app_context():
    try:
        db.create_all()
    except Exception:
        db.session.rollback()
        db.drop_all()
        db.create_all()
    
    if not Usuario.query.filter_by(username='IverPerez').first():
        db.session.add(Usuario(username='IverPerez', password='123456789'))
        db.session.commit()

# ─────────────────────────────────────────
#  RUTAS
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
        flash('Credenciales incorrectas', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user_id' not in session: return redirect(url_for('login'))
    productos = Producto.query.order_by(Producto.nombre).all()
    ventas = Venta.query.order_by(Venta.id.desc()).all()
    carrito = session.get('carrito', [])
    total_carrito = sum(float(item['subtotal']) for item in carrito)
    return render_template('index.html', productos=productos, ventas=ventas, carrito=carrito, total_carrito=total_carrito)

@app.route('/registrar', methods=['POST'])
def registrar():
    if 'user_id' not in session: return redirect(url_for('login'))
    nuevo = Producto(
        codigo=request.form.get('codigo'),
        nombre=request.form.get('nombre'),
        precio_docena=float(request.form.get('precio')),
        stock_unidades=int(request.form.get('stock'))
    )
    db.session.add(nuevo)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/agregar_al_carrito', methods=['POST'])
def agregar_al_carrito():
    prod_id = request.form.get('producto_id')
    cant = int(request.form.get('cantidad', 1))
    prod = Producto.query.get(prod_id)
    if prod and prod.stock_unidades >= cant:
        sub = (float(prod.precio_docena) / 12) * cant
        carrito = session.get('carrito', [])
        carrito.append({'id': prod.id, 'nombre': prod.nombre, 'cantidad': cant, 'subtotal': sub})
        session['carrito'] = carrito
    else:
        flash('Stock insuficiente', 'warning')
    return redirect(url_for('index'))

@app.route('/finalizar_venta', methods=['POST'])
def finalizar_venta():
    carrito = session.get('carrito', [])
    if not carrito: return redirect(url_for('index'))
    cliente = request.form.get('cliente', 'Consumidor Final')
    total_v = sum(float(item['subtotal']) for item in carrito)
    
    nueva_v = Venta(cliente_nombre=cliente, total_general=total_v)
    db.session.add(nueva_v)
    db.session.flush()
    
    for item in carrito:
        p = Producto.query.get(item['id'])
        p.stock_unidades -= item['cantidad']
        db.session.add(DetalleVenta(venta_id=nueva_v.id, producto_nombre=item['nombre'], cantidad=item['cantidad'], subtotal=item['subtotal']))
    
    db.session.commit()
    session.pop('carrito', None)
    flash('Venta registrada con éxito', 'success')
    return redirect(url_for('index'))

@app.route('/limpiar_carrito')
def limpiar_carrito():
    session.pop('carrito', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)