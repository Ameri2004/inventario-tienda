import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, inspect
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# ─── CONFIGURACIÓN SEGURA ────────────────────────────────────────────────────
app.secret_key = os.environ.get('SECRET_KEY', 'clave-secreta-local-dev')

# Fix para Render: postgres:// → postgresql://
database_url = os.environ.get('DATABASE_URL', 'sqlite:///inventario.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Sesión segura para producción en Render
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True

db = SQLAlchemy(app)


# ─── MODELOS ─────────────────────────────────────────────────────────────────

class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Producto(db.Model):
    __tablename__ = 'productos'
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    precio_docena = db.Column(db.Float, nullable=False)
    stock_unidades = db.Column(db.Integer, default=0)

    @property
    def precio_unitario(self):
        return round(self.precio_docena / 12, 2)


class Venta(db.Model):
    __tablename__ = 'ventas'
    id = db.Column(db.Integer, primary_key=True)
    cliente = db.Column(db.String(120), nullable=False, default='Cliente General')
    total = db.Column(db.Float, nullable=False, default=0.0)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    detalles = db.relationship('DetalleVenta', backref='venta', lazy=True, cascade='all, delete-orphan')


class DetalleVenta(db.Model):
    __tablename__ = 'detalle_ventas'
    id = db.Column(db.Integer, primary_key=True)
    venta_id = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False)
    nombre_producto = db.Column(db.String(120), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Float, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    producto = db.relationship('Producto', backref='detalles_venta')


# ─── INICIALIZACIÓN SEGURA DE LA BASE DE DATOS ───────────────────────────────
# Esta función maneja la discrepancia entre la estructura antigua y la nueva.
# Estrategia: detectar si las columnas nuevas existen; si no, hacer drop y recrear.

def inicializar_bd():
    with app.app_context():
        inspector = inspect(db.engine)
        tablas_existentes = inspector.get_table_names()
        necesita_recrear = False

        # Verificar si la tabla 'ventas' tiene la estructura nueva
        if 'ventas' in tablas_existentes:
            columnas_ventas = [c['name'] for c in inspector.get_columns('ventas')]
            # La nueva estructura requiere las columnas: id, cliente, total, fecha
            columnas_requeridas = {'id', 'cliente', 'total', 'fecha'}
            if not columnas_requeridas.issubset(set(columnas_ventas)):
                necesita_recrear = True

        # Verificar si la tabla 'detalle_ventas' existe
        if 'detalle_ventas' not in tablas_existentes:
            necesita_recrear = True

        if necesita_recrear:
            print("⚠️  Estructura antigua detectada. Recreando tablas de ventas...")
            try:
                # Solo eliminar las tablas de ventas (no productos ni usuarios)
                with db.engine.connect() as conn:
                    conn.execute(text('DROP TABLE IF EXISTS detalle_ventas CASCADE'))
                    conn.execute(text('DROP TABLE IF EXISTS ventas CASCADE'))
                    conn.commit()
                print("✅ Tablas antiguas eliminadas correctamente.")
            except Exception as e:
                print(f"⚠️  No se pudieron eliminar tablas: {e}")

        # Crear todas las tablas que falten (no afecta las que ya existen)
        db.create_all()
        print("✅ Tablas verificadas/creadas correctamente.")

        # Crear usuario por defecto si no existe
        if not Usuario.query.filter_by(username='IverPerez').first():
            admin = Usuario(username='IverPerez')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("✅ Usuario IverPerez creado.")


# Ejecutar inicialización al arrancar
inicializar_bd()


# ─── DECORADOR DE AUTENTICACIÓN ───────────────────────────────────────────────

def login_requerido(f):
    from functools import wraps
    @wraps(f)
    def decorado(*args, **kwargs):
        if 'usuario_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorado


# ─── RUTAS DE AUTENTICACIÓN ───────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        usuario = Usuario.query.filter_by(username=username).first()
        if usuario and usuario.check_password(password):
            session.permanent = True
            session['usuario_id'] = usuario.id
            session['username'] = usuario.username
            flash('Sesión iniciada correctamente.', 'success')
            return redirect(url_for('index'))
        flash('Usuario o contraseña incorrectos.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada.', 'info')
    return redirect(url_for('login'))


# ─── RUTA PRINCIPAL ───────────────────────────────────────────────────────────

@app.route('/')
@login_requerido
def index():
    productos = Producto.query.order_by(Producto.nombre).all()
    ventas = Venta.query.order_by(Venta.fecha.desc()).limit(20).all()
    carrito = session.get('carrito', [])

    # Calcular total del carrito
    total_carrito = sum(item['subtotal'] for item in carrito)

    return render_template('index.html',
                           productos=productos,
                           ventas=ventas,
                           carrito=carrito,
                           total_carrito=total_carrito)


# ─── RUTAS DE PRODUCTOS ───────────────────────────────────────────────────────

@app.route('/agregar_producto', methods=['POST'])
@login_requerido
def agregar_producto():
    codigo = request.form.get('codigo', '').strip()
    nombre = request.form.get('nombre', '').strip()
    precio_docena = request.form.get('precio_docena', 0)
    stock_unidades = request.form.get('stock_unidades', 0)

    if not codigo or not nombre:
        flash('Código y nombre son obligatorios.', 'danger')
        return redirect(url_for('index'))

    try:
        precio_docena = float(precio_docena)
        stock_unidades = int(stock_unidades)
    except ValueError:
        flash('Precio y stock deben ser numéricos.', 'danger')
        return redirect(url_for('index'))

    # Verificar si el código ya existe
    existente = Producto.query.filter_by(codigo=codigo).first()
    if existente:
        flash(f'El código "{codigo}" ya existe.', 'warning')
        return redirect(url_for('index'))

    producto = Producto(
        codigo=codigo,
        nombre=nombre,
        precio_docena=precio_docena,
        stock_unidades=stock_unidades
    )
    db.session.add(producto)
    db.session.commit()
    flash(f'Producto "{nombre}" registrado correctamente.', 'success')
    return redirect(url_for('index'))


@app.route('/eliminar_producto/<int:producto_id>', methods=['POST'])
@login_requerido
def eliminar_producto(producto_id):
    producto = Producto.query.get_or_404(producto_id)
    db.session.delete(producto)
    db.session.commit()
    flash(f'Producto "{producto.nombre}" eliminado.', 'info')
    return redirect(url_for('index'))


# ─── RUTAS DEL CARRITO ────────────────────────────────────────────────────────

@app.route('/agregar_al_carrito/<int:producto_id>', methods=['POST'])
@login_requerido
def agregar_al_carrito(producto_id):
    producto = Producto.query.get_or_404(producto_id)
    cantidad = int(request.form.get('cantidad', 1))

    if cantidad <= 0:
        flash('La cantidad debe ser mayor a 0.', 'warning')
        return redirect(url_for('index'))

    if cantidad > producto.stock_unidades:
        flash(f'Stock insuficiente. Disponible: {producto.stock_unidades} unidades.', 'danger')
        return redirect(url_for('index'))

    carrito = session.get('carrito', [])

    # Verificar si el producto ya está en el carrito
    encontrado = False
    for item in carrito:
        if item['producto_id'] == producto_id:
            nueva_cantidad = item['cantidad'] + cantidad
            if nueva_cantidad > producto.stock_unidades:
                flash(f'No hay suficiente stock. Disponible: {producto.stock_unidades} unidades.', 'danger')
                return redirect(url_for('index'))
            item['cantidad'] = nueva_cantidad
            item['subtotal'] = round(nueva_cantidad * producto.precio_unitario, 2)
            encontrado = True
            break

    if not encontrado:
        carrito.append({
            'producto_id': producto_id,
            'nombre': producto.nombre,
            'codigo': producto.codigo,
            'precio_unitario': producto.precio_unitario,
            'cantidad': cantidad,
            'subtotal': round(cantidad * producto.precio_unitario, 2)
        })

    session['carrito'] = carrito
    session.modified = True
    flash(f'"{producto.nombre}" agregado al carrito.', 'success')
    return redirect(url_for('index'))


@app.route('/quitar_del_carrito/<int:producto_id>', methods=['POST'])
@login_requerido
def quitar_del_carrito(producto_id):
    carrito = session.get('carrito', [])
    carrito = [item for item in carrito if item['producto_id'] != producto_id]
    session['carrito'] = carrito
    session.modified = True
    flash('Producto removido del carrito.', 'info')
    return redirect(url_for('index'))


@app.route('/vaciar_carrito', methods=['POST'])
@login_requerido
def vaciar_carrito():
    session['carrito'] = []
    session.modified = True
    flash('Carrito vaciado.', 'info')
    return redirect(url_for('index'))


@app.route('/finalizar_venta', methods=['POST'])
@login_requerido
def finalizar_venta():
    carrito = session.get('carrito', [])
    if not carrito:
        flash('El carrito está vacío.', 'warning')
        return redirect(url_for('index'))

    cliente = request.form.get('cliente', 'Cliente General').strip()
    if not cliente:
        cliente = 'Cliente General'

    try:
        total_general = 0.0
        nueva_venta = Venta(cliente=cliente, total=0.0)
        db.session.add(nueva_venta)
        db.session.flush()  # Obtener el ID de la venta antes del commit

        for item in carrito:
            producto = Producto.query.get(item['producto_id'])
            if not producto:
                raise ValueError(f"Producto ID {item['producto_id']} no encontrado.")
            if item['cantidad'] > producto.stock_unidades:
                raise ValueError(f"Stock insuficiente para '{producto.nombre}'. "
                                 f"Disponible: {producto.stock_unidades}, solicitado: {item['cantidad']}.")

            # Descontar stock
            producto.stock_unidades -= item['cantidad']

            # Crear detalle
            detalle = DetalleVenta(
                venta_id=nueva_venta.id,
                producto_id=producto.id,
                nombre_producto=producto.nombre,
                cantidad=item['cantidad'],
                precio_unitario=item['precio_unitario'],
                subtotal=item['subtotal']
            )
            db.session.add(detalle)
            total_general += item['subtotal']

        nueva_venta.total = round(total_general, 2)
        db.session.commit()

        # Limpiar carrito
        session['carrito'] = []
        session.modified = True

        flash(f'✅ Venta #{nueva_venta.id} registrada por Bs. {nueva_venta.total:.2f}. '
              f'Cliente: {cliente}', 'success')

    except ValueError as e:
        db.session.rollback()
        flash(f'Error al procesar la venta: {str(e)}', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error inesperado: {str(e)}', 'danger')

    return redirect(url_for('index'))


# ─── RUTA DE DETALLE DE VENTA ─────────────────────────────────────────────────

@app.route('/venta/<int:venta_id>')
@login_requerido
def detalle_venta(venta_id):
    venta = Venta.query.get_or_404(venta_id)
    return render_template('detalle_venta.html', venta=venta)


# ─── PUNTO DE ENTRADA ─────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)