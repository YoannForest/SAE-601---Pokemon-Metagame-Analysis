@echo off

if not exist "env\" (
    echo Création de l'environnement virtuel...
    python -m venv env
)

call env\Scripts\activate.bat

pip install --upgrade pip
pip install streamlit
pip install psycopg2
pip install plotly
pip install collections
streamlit run app.py


