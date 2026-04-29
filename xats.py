# Exemple de com guardar cada missatge a SQL
import sqlite3

def guardar_missatge(usuari, rol, contingut):
    conn = sqlite3.connect('fitness_saas.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS historial (usuari TEXT, rol TEXT, missatge TEXT)')
    c.execute('INSERT INTO historial VALUES (?, ?, ?)', (usuari, rol, contingut))
    conn.commit()
    conn.close()