from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, inspect
from datetime import datetime
import os

app = Flask(__name__)

# ─────────────────────────────────────────
#  CONFIGURACIÓN  (idéntica a la que tenías)
# ─────────────────────────────────────────
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
    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)


class Producto(db.Model):
    __tablename__ = 'productos'
    id             = db.Column(db.Integer, primary_key=True)
    codigo         = db.Column(db.String(50), unique=True, nullable=False)
    nombre         = db.Column(db.String(150), nullable=False)
    precio_docena  = db.Column(db.Numeric(10, 2), nullable=False)
    stock_unidades = db.Column(db.Integer, default=0)

    @property
    def precio_unitario(self):
        """Precio por unidad = precio docena / 12"""
        return round(float(self.precio_docena) / 12, 2)


class Venta(db.Model):
    """
    MISMOS nombres de columna que ya tenías (id, fecha, cliente_nombre, total_general).
    Se agrega la relación con DetalleVenta.
    """
    __tablename__ = 'ventas'
    id             = db.Column(db.Integer, primary_key=True)
    fecha          = db.Column(db.DateTime, default=datetime.now)
    cliente_nombre = db.Column(db.String(150), default='Consumidor Final')
    total_general  = db.Column(db.Numeric(10, 2), nullable=False)
    detalles       = db.relationship('DetalleVenta', backref='venta',
                                     lazy=True, cascade='all, delete-orphan')


class DetalleVenta(db.Model):
    """Tabla NUEVA – guarda cada producto de una venta."""
    __tablename__ = 'detalle_ventas'
    id              = db.Column(db.Integer, primary_key=True)
    venta_id        = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=False)
    producto_id     = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False)
    nombre_producto = db.Column(db.String(150), nullable=False)
    cantidad        = db.Column(db.Integer, nullable=False)
    precio_unit     = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal        = db.Column(db.Numeric(10, 2), nullable=False)
    producto        = db.relationship('Producto')


# ─────────────────────────────────────────
#  PARCHE ANTI-ERROR 500
#  Compara la estructura real de la BD con la esperada.
#  Si detecta la estructura VIEJA, elimina SOLO las tablas de ventas
#  (nunca toca 'productos' ni 'usuarios') y las recrea.
# ─────────────────────────────────────────

def inicializar_bd():
    with app.app_context():
        inspector = inspect(db.engine)
        tablas    = inspector.get_table_names()
        recrear   = False

        # La tabla 'detalle_ventas' no existía en la estructura vieja
        if 'detalle_ventas' not in tablas:
            recrear = True

        # Verificación extra de columnas en 'ventas'
        if 'ventas' in tablas:
            cols = {c['name'] for c in inspector.get_columns('ventas')}
            if not {'id', 'fecha', 'cliente_nombre', 'total_general'}.issubset(cols):
                recrear = True

        if recrear:
            print("⚠️  Estructura antigua detectada → reconstruyendo tablas de ventas…")
            try:
                with db.engine.connect() as conn:
                    conn.execute(text('DROP TABLE IF EXISTS detalle_ventas CASCADE'))
                    conn.execute(text('DROP TABLE IF EXISTS ventas CASCADE'))
                    conn.commit()
                print("✅ Tablas antiguas eliminadas.")
            except Exception as e:
                print(f"   (aviso): {e}")

        # Crea todas las tablas faltantes (no toca las existentes)
        db.create_all()
        print("✅ Base de datos lista.")

        # Usuario por defecto (igual que antes)
        if not Usuario.query.filter_by(username='IverPerez').first():
            db.session.add(Usuario(username='IverPerez', password='123456789'))
            db.session.commit()
            print("✅ Usuario IverPerez creado.")


inicializar_bd()


# ─────────────────────────────────────────
#  AUTENTICACIÓN
# ─────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u    = request.form.get('username')
        p    = request.form.get('password')
        user = Usuario.query.filter_by(username=u, password=p).first()
        if user:
            session.permanent   = True
            session['user_id']  = user.id
            session['username'] = user.username
            return redirect(url_for('index'))
        flash('Credenciales incorrectas', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ─────────────────────────────────────────
#  ÍNDICE PRINCIPAL
# ─────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    productos     = Producto.query.order_by(Producto.nombre).all()
    ventas        = Venta.query.order_by(Venta.id.desc()).all()
    carrito       = session.get('carrito', [])
    total_carrito = sum(float(item['subtotal']) for item in carrito)
    return render_template('index.html',
                           productos=productos,
                           ventas=ventas,
                           carrito=carrito,
                           total_carrito=total_carrito)


# ─────────────────────────────────────────
#  PRODUCTOS
# ─────────────────────────────────────────

@app.route('/registrar', methods=['POST'])
def registrar():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    codigo = request.form.get('codigo', '').strip()
    nombre = request.form.get('nombre', '').strip()

    if Producto.query.filter_by(codigo=codigo).first():
        flash(f'El código "{codigo}" ya existe.', 'warning')
        return redirect(url_for('index'))

    nuevo = Producto(
        codigo         = codigo,
        nombre         = nombre,
        precio_docena  = float(request.form.get('precio', 0)),
        stock_unidades = int(request.form.get('stock', 0))
    )
    db.session.add(nuevo)
    db.session.commit()
    flash(f'Producto "{nombre}" registrado.', 'success')
    return redirect(url_for('index'))


@app.route('/eliminar_producto/<int:pid>', methods=['POST'])
def eliminar_producto(pid):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    p = Producto.query.get_or_404(pid)
    db.session.delete(p)
    db.session.commit()
    flash(f'Producto "{p.nombre}" eliminado.', 'info')
    return redirect(url_for('index'))


# ─────────────────────────────────────────
#  CARRITO  (almacenado en session del navegador, sin tocar la BD)
# ─────────────────────────────────────────

@app.route('/agregar_al_carrito', methods=['POST'])
def agregar_al_carrito():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    prod_id = int(request.form.get('producto_id'))
    cant    = int(request.form.get('cantidad', 1))
    prod    = Producto.query.get(prod_id)

    if not prod:
        flash('Producto no encontrado.', 'danger')
        return redirect(url_for('index'))
    if cant <= 0:
        flash('La cantidad debe ser mayor a 0.', 'warning')
        return redirect(url_for('index'))
    if cant > prod.stock_unidades:
        flash(f'Stock insuficiente. Disponible: {prod.stock_unidades} uds.', 'danger')
        return redirect(url_for('index'))

    carrito = session.get('carrito', [])

    # Si el producto ya está, acumula la cantidad
    for item in carrito:
        if item['id'] == prod_id:
            nueva_cant = item['cantidad'] + cant
            if nueva_cant > prod.stock_unidades:
                flash(f'Stock insuficiente. Disponible: {prod.stock_unidades} uds.', 'danger')
                return redirect(url_for('index'))
            item['cantidad'] = nueva_cant
            item['subtotal'] = round(prod.precio_unitario * nueva_cant, 2)
            session['carrito'] = carrito
            session.modified   = True
            flash(f'"{prod.nombre}" actualizado en el carrito.', 'success')
            return redirect(url_for('index'))

    carrito.append({
        'id':         prod_id,
        'nombre':     prod.nombre,
        'cantidad':   cant,
        'precio_unit': prod.precio_unitario,
        'subtotal':   round(prod.precio_unitario * cant, 2)
    })
    session['carrito'] = carrito
    session.modified   = True
    flash(f'"{prod.nombre}" agregado al carrito.', 'success')
    return redirect(url_for('index'))


@app.route('/quitar_del_carrito/<int:prod_id>', methods=['POST'])
def quitar_del_carrito(prod_id):
    carrito = session.get('carrito', [])
    session['carrito'] = [i for i in carrito if i['id'] != prod_id]
    session.modified   = True
    flash('Producto quitado del carrito.', 'info')
    return redirect(url_for('index'))


@app.route('/limpiar_carrito')
def limpiar_carrito():
    """Ruta GET que ya tenías — sigue funcionando igual."""
    session.pop('carrito', None)
    return redirect(url_for('index'))


# ─────────────────────────────────────────
#  FINALIZAR VENTA
# ─────────────────────────────────────────

@app.route('/finalizar_venta', methods=['POST'])
def finalizar_venta():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    carrito = session.get('carrito', [])
    if not carrito:
        flash('El carrito está vacío.', 'warning')
        return redirect(url_for('index'))

    cliente = request.form.get('cliente', 'Consumidor Final').strip() or 'Consumidor Final'
    total_v = round(sum(float(i['subtotal']) for i in carrito), 2)

    try:
        nueva_v = Venta(cliente_nombre=cliente, total_general=total_v)
        db.session.add(nueva_v)
        db.session.flush()   # necesario para obtener nueva_v.id

        for item in carrito:
            p = Producto.query.get(item['id'])
            if not p:
                raise ValueError(f"Producto ID {item['id']} no encontrado.")
            if item['cantidad'] > p.stock_unidades:
                raise ValueError(f"Stock insuficiente para '{p.nombre}'.")

            p.stock_unidades -= item['cantidad']

            db.session.add(DetalleVenta(
                venta_id        = nueva_v.id,
                producto_id     = p.id,
                nombre_producto = p.nombre,
                cantidad        = item['cantidad'],
                precio_unit     = item['precio_unit'],
                subtotal        = item['subtotal']
            ))

        db.session.commit()
        session.pop('carrito', None)
        flash(f'✅ Venta #{nueva_v.id} registrada — Total: Bs. {total_v:.2f}', 'success')
        # Redirige a venta.html (comprobante)
        return redirect(url_for('ver_venta', venta_id=nueva_v.id))

    except ValueError as e:
        db.session.rollback()
        flash(f'Error: {e}', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error inesperado: {e}', 'danger')

    return redirect(url_for('index'))


# ─────────────────────────────────────────
#  COMPROBANTE  →  venta.html
# ─────────────────────────────────────────

@app.route('/venta/<int:venta_id>')
def ver_venta(venta_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    venta = Venta.query.get_or_404(venta_id)
    return render_template('venta.html', venta=venta)


# ─────────────────────────────────────────
#  FACTURA IMPRIMIBLE  →  factura.html
# ─────────────────────────────────────────

@app.route('/factura/<int:venta_id>')
def factura(venta_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    venta = Venta.query.get_or_404(venta_id)
    return render_template('factura.html', venta=venta)


# ─────────────────────────────────────────
#  ARRANQUE
# ─────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)