from flask import Flask, request, jsonify, send_from_directory
import os
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from flask_cors import CORS

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# Konfigurace databáze - PostgreSQL pro Render
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    # Fallback pro lokální vývoj
    DATABASE_URL = "postgresql://localhost/crystal_game"

# Connection pool pro PostgreSQL
connection_pool = None

def init_connection_pool():
    global connection_pool
    try:
        connection_pool = ConnectionPool(
            DATABASE_URL,
            min_size=1,
            max_size=20
        )
        print("Connection pool vytvořen úspěšně")
    except Exception as e:
        print(f"Chyba při vytváření connection poolu: {e}")

def get_db_connection():
    """Získá připojení z poolu"""
    global connection_pool
    if connection_pool:
        try:
            return connection_pool.getconn()
        except Exception as e:
            print(f"Chyba při získávání připojení z poolu: {e}")
    
    # Fallback - přímé připojení
    try:
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)
    except Exception as e:
        print(f"Chyba při přímém připojení: {e}")
        return None

def return_db_connection(conn):
    """Vrátí připojení zpět do poolu"""
    global connection_pool
    if connection_pool and conn:
        try:
            connection_pool.putconn(conn)
        except Exception as e:
            print(f"Chyba při vracení připojení: {e}")
            conn.close()
    elif conn:
        conn.close()

# Zajištění, že tabulka existuje
def init_database():
    conn = get_db_connection()
    if not conn:
        print("Nelze se připojit k databázi!")
        return
        
    cursor = conn.cursor()
    try:
        # Vytvoření tabulky pro PostgreSQL
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS crystal_game_data (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                crystals INTEGER DEFAULT 0,
                autoclickers INTEGER DEFAULT 0,
                factories INTEGER DEFAULT 0,
                mines INTEGER DEFAULT 0,
                refineries INTEGER DEFAULT 0,
                quantumDrills INTEGER DEFAULT 0,
                clickPower INTEGER DEFAULT 1,
                totalClicks INTEGER DEFAULT 0,
                priceAutoclicker INTEGER DEFAULT 5,
                priceFactory INTEGER DEFAULT 50,
                priceMine INTEGER DEFAULT 500,
                priceRefinery INTEGER DEFAULT 5000,
                priceQuantumDrill INTEGER DEFAULT 50000,
                priceClickPower INTEGER DEFAULT 20,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        
        # Vytvoření indexů pro výkon
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_crystals ON crystal_game_data(crystals)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_username ON crystal_game_data(username)")
        
        conn.commit()
        print("Databáze inicializována úspěšně")
    except Exception as e:
        print(f"Chyba při inicializaci databáze: {e}")
        conn.rollback()
    finally:
        cursor.close()
        return_db_connection(conn)

# Posílání hlavní stránky
@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

# Health check pro Render
@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200

# Registrace
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not username or not password:
        return jsonify({'success': False, 'message': 'Uživatelské jméno a heslo jsou povinné'}), 400
    
    if len(username) > 50:
        return jsonify({'success': False, 'message': 'Uživatelské jméno je příliš dlouhé'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Chyba databáze'}), 500
        
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id FROM crystal_game_data WHERE username = %s", (username,))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': 'Uživatel již existuje'}), 400

        cursor.execute(
            "INSERT INTO crystal_game_data (username, password) VALUES (%s, %s)", 
            (username, password)
        )
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        print(f"Chyba registrace: {e}")
        conn.rollback()
        return jsonify({'success': False, 'message': 'Chyba při registraci'}), 500
    finally:
        cursor.close()
        return_db_connection(conn)

# Přihlášení
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Chyba databáze'}), 500
        
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT id FROM crystal_game_data WHERE username = %s AND password = %s", 
            (username, password)
        )
        result = cursor.fetchone()
        if result:
            return jsonify({'success': True, 'user_id': result['id']})
        else:
            return jsonify({'success': False, 'message': 'Špatné přihlašovací údaje'}), 401
    except Exception as e:
        print(f"Chyba přihlášení: {e}")
        return jsonify({'success': False, 'message': 'Chyba při přihlašování'}), 500
    finally:
        cursor.close()
        return_db_connection(conn)

# Uložení hry
@app.route('/save_game', methods=['POST'])
def save_game():
    data = request.get_json()
    user_id = data.get('user_id')
    gd = data.get('game_data', {})

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Chyba databáze'}), 500
        
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """
            UPDATE crystal_game_data SET
                crystals=%s,
                autoclickers=%s,
                factories=%s,
                mines=%s,
                refineries=%s,
                quantumDrills=%s,
                clickPower=%s,
                totalClicks=%s,
                priceAutoclicker=%s,
                priceFactory=%s,
                priceMine=%s,
                priceRefinery=%s,
                priceQuantumDrill=%s,
                priceClickPower=%s,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
            """,
            (
                gd.get('crystals', 0),
                gd.get('autoclickers', 0),
                gd.get('factories', 0),
                gd.get('mines', 0),
                gd.get('refineries', 0),
                gd.get('quantumDrills', 0),
                gd.get('clickPower', 1),
                gd.get('totalClicks', 0),
                gd.get('priceAutoclicker', 5),
                gd.get('priceFactory', 50),
                gd.get('priceMine', 500),
                gd.get('priceRefinery', 5000),
                gd.get('priceQuantumDrill', 50000),
                gd.get('priceClickPower', 20),
                user_id
            )
        )
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        print(f"Chyba ukládání: {e}")
        conn.rollback()
        return jsonify({'success': False, 'message': 'Chyba při ukládání'}), 500
    finally:
        cursor.close()
        return_db_connection(conn)

# Načtení hry
@app.route('/load_game')
def load_game():
    user_id = request.args.get('user_id')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Chyba databáze'}), 500
        
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM crystal_game_data WHERE id = %s", (user_id,))
        row = cursor.fetchone()

        if not row:
            return jsonify({'success': False, 'message': 'Hráč nenalezen'}), 404

        game_data = {
            'crystals': row.get('crystals', 0),
            'autoclickers': row.get('autoclickers', 0),
            'factories': row.get('factories', 0),
            'mines': row.get('mines', 0),
            'refineries': row.get('refineries', 0),
            'quantumDrills': row.get('quantumdrills', 0),  # PostgreSQL lowercase
            'clickPower': row.get('clickpower', 1),
            'totalClicks': row.get('totalclicks', 0),
            'priceAutoclicker': row.get('priceautoclicker', 5),
            'priceFactory': row.get('pricefactory', 50),
            'priceMine': row.get('pricemine', 500),
            'priceRefinery': row.get('pricerefinery', 5000),
            'priceQuantumDrill': row.get('pricequantumdrill', 50000),
            'priceClickPower': row.get('priceclickpower', 20)
        }

        return jsonify({'success': True, 'game_data': game_data})
    except Exception as e:
        print(f"Chyba načítání: {e}")
        return jsonify({'success': False, 'message': 'Chyba při načítání'}), 500
    finally:
        cursor.close()
        return_db_connection(conn)

# Endpoint pro žebříček
@app.route('/leaderboard')
def leaderboard():
    leaderboard_type = request.args.get('type', 'crystals')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Chyba databáze'}), 500
        
    cursor = conn.cursor()
    
    try:
        # Definujeme různé typy žebříčků
        if leaderboard_type == 'crystals':
            query = """
            SELECT username, COALESCE(crystals, 0) as value 
            FROM crystal_game_data 
            WHERE COALESCE(crystals, 0) > 0 
            ORDER BY COALESCE(crystals, 0) DESC 
            LIMIT 10
            """
            label = "Křišťály"
        elif leaderboard_type == 'cps':
            query = """
            SELECT username, 
                   (COALESCE(autoclickers, 0) * 1 + COALESCE(factories, 0) * 5 + COALESCE(mines, 0) * 50 + COALESCE(refineries, 0) * 200 + COALESCE(quantumDrills, 0) * 1000) as value
            FROM crystal_game_data 
            WHERE (COALESCE(autoclickers, 0) * 1 + COALESCE(factories, 0) * 5 + COALESCE(mines, 0) * 50 + COALESCE(refineries, 0) * 200 + COALESCE(quantumDrills, 0) * 1000) > 0
            ORDER BY value DESC 
            LIMIT 10
            """
            label = "CPS"
        elif leaderboard_type == 'clicks':
            query = """
            SELECT username, COALESCE(totalClicks, 0) as value 
            FROM crystal_game_data 
            WHERE COALESCE(totalClicks, 0) > 0 
            ORDER BY COALESCE(totalClicks, 0) DESC 
            LIMIT 10
            """
            label = "Celkové kliky"
        elif leaderboard_type == 'buildings':
            query = """
            SELECT username, 
                   (COALESCE(autoclickers, 0) + COALESCE(factories, 0) + COALESCE(mines, 0) + COALESCE(refineries, 0) + COALESCE(quantumDrills, 0)) as value
            FROM crystal_game_data 
            WHERE (COALESCE(autoclickers, 0) + COALESCE(factories, 0) + COALESCE(mines, 0) + COALESCE(refineries, 0) + COALESCE(quantumDrills, 0)) > 0
            ORDER BY value DESC 
            LIMIT 10
            """
            label = "Celkové budovy"
        else:
            return jsonify({'success': False, 'message': 'Neplatný typ žebříčku'}), 400

        cursor.execute(query)
        results = cursor.fetchall()
        
        leaderboard_data = []
        for i, row in enumerate(results, 1):
            leaderboard_data.append({
                'rank': i,
                'username': row['username'],
                'value': int(row['value']) if row['value'] is not None else 0
            })
        
        return jsonify({
            'success': True, 
            'leaderboard': leaderboard_data,
            'label': label,
            'type': leaderboard_type
        })
        
    except Exception as e:
        print(f"Chyba žebříčku: {e}")
        return jsonify({'success': False, 'message': 'Chyba při načítání žebříčku'}), 500
    finally:
        cursor.close()
        return_db_connection(conn)

# Statistiky pro admina
@app.route('/stats')
def stats():
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Chyba databáze'}), 500
        
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) as total_players FROM crystal_game_data")
        total_players = cursor.fetchone()['total_players']
        
        cursor.execute("SELECT SUM(crystals) as total_crystals FROM crystal_game_data")
        total_crystals = cursor.fetchone()['total_crystals'] or 0
        
        cursor.execute("SELECT SUM(totalClicks) as total_clicks FROM crystal_game_data")
        total_clicks = cursor.fetchone()['total_clicks'] or 0
        
        return jsonify({
            'success': True,
            'stats': {
                'total_players': total_players,
                'total_crystals': total_crystals,
                'total_clicks': total_clicks
            }
        })
    except Exception as e:
        print(f"Chyba statistik: {e}")
        return jsonify({'success': False, 'message': 'Chyba při načítání statistik'}), 500
    finally:
        cursor.close()
        return_db_connection(conn)

# Inicializace při startu
init_connection_pool()
init_database()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
