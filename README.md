# AusPost Contractors Invoicer

Aplicación Flask para contratistas de Australia Post con roles (admin/worker), carga diaria de paquetes y facturación (super + GST + alquiler van). Lista para **Render** con **PostgreSQL** y **Gunicorn**.

## Deploy en Render (desde GitHub)
1. Crea un repo en GitHub y sube **el contenido** de esta carpeta (no la carpeta entera).
2. En Render: **New → Web Service → GitHub → selecciona el repo**.
3. Configura:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
4. Crea **PostgreSQL** en Render y copia la **Internal Database URL**.
5. En tu Web Service → **Environment** agrega:
   - `DATABASE_URL` = (URL de Postgres)
   - `SECRET_KEY` = (cadena aleatoria segura)
6. Deploy. Accede a la URL pública. Login: `admin@example.com` / `admin123`.

## Desarrollo local rápido
```bash
python -m venv venv
venv\Scripts\activate   # Windows (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
set DATABASE_URL=sqlite:///auspost.db  # opcional para SQLite local
python app.py
```
