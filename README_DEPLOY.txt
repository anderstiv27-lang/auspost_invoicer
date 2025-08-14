DEPLOY EN RENDER (resumen)
1) Crea Postgres en Render y copia la Internal Database URL.
2) Crea Web Service desde GitHub (o desde repo privado conectado). 
   - Build: pip install -r requirements.txt
   - Start: gunicorn app:app
3) En Environment agrega:
   - DATABASE_URL = (URL de Postgres)
   - SECRET_KEY = (cadena aleatoria segura)
4) Deploy. Login inicial: admin@example.com / admin123
