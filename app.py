from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os # Importamos os para leer las variables de entorno de Render

app = Flask(__name__)

# --- CONFIGURACIÓN DE BASE DE DATOS (REEMPLAZADA) ---
# Si existe la variable 'DATABASE_URL' (en Render), la usa. 
# Si no, usa tu base de datos local de PostgreSQL.
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 
    'postgresql://postgres:orly123@localhost:5432/tienda_uab_v3'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'clave_secreta_orly_2026' 

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

# Crear tablas y usuario administrador inicial
with app.app_context():
    db.create_all()
    if not Usuario.query.filter_by(username='admin').first():
        db.session.add(Usuario(username='admin', password='orly123'))
        db.session.commit()

# ─────────────────────────────────────────
#  RUTAS DE ACCESO (LOGIN)
# ─────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username')
        p = request.form.get('password')
        user = Usuario.query.filter_by(username=u, password=p).first()
        if user:
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('index'))
        flash('Credenciales incorrectas', 'danger')
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
        return redirect(url_for('login'))
    
    productos = Producto.query.order_by(Producto.nombre).all()
    ventas = Venta.query.order_by(Venta.id.desc()).all()
    gran_total = sum(float(v.total) for v in ventas)
    
    return render_template('index.html', productos=productos, ventas=ventas, gran_total=gran_total)

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
    # Usamos el puerto que Render nos asigne, o el 8000 por defecto
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)