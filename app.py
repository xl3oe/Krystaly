from flask import Flask, request, jsonify, send_from_directory
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool
from flask_cors import CORS
import math
import random
import time

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
        connection_pool = psycopg2.pool.SimpleConnectionPool(
            1, 20,  # min a max připojení
            DATABASE_URL,
            cursor_factory=RealDictCursor
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
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
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
        # Vytvoření tabulky pro PostgreSQL s novými položkami
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS crystal_game_data (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                crystals BIGINT DEFAULT 0,
                lifetime_crystals BIGINT DEFAULT 0,
                autoclickers INTEGER DEFAULT 0,
                factories INTEGER DEFAULT 0,
                mines INTEGER DEFAULT 0,
                refineries INTEGER DEFAULT 0,
                quantumDrills INTEGER DEFAULT 0,
                magicWells INTEGER DEFAULT 0,
                starForges INTEGER DEFAULT 0,
                timeAccelerators INTEGER DEFAULT 0,
                voidHarvesters INTEGER DEFAULT 0,
                clickPower INTEGER DEFAULT 1,
                totalClicks INTEGER DEFAULT 0,
                priceAutoclicker INTEGER DEFAULT 5,
                priceFactory INTEGER DEFAULT 50,
                priceMine INTEGER DEFAULT 500,
                priceRefinery INTEGER DEFAULT 5000,
                priceQuantumDrill INTEGER DEFAULT 50000,
                priceMagicWell INTEGER DEFAULT 500000,
                priceStarForge INTEGER DEFAULT 5000000,
                priceTimeAccelerator INTEGER DEFAULT 50000000,
                priceVoidHarvester INTEGER DEFAULT 1000000000,
                priceClickPower INTEGER DEFAULT 20,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                rebirthCount INTEGER DEFAULT 0,
                rebirthPoints INTEGER DEFAULT 0,
                bonusClickPower INTEGER DEFAULT 0,
                bonusProduction INTEGER DEFAULT 0,
                bonusRebirthPoints INTEGER DEFAULT 0,
                luckLevel INTEGER DEFAULT 0,
                mysteryBoxes INTEGER DEFAULT 0,
                lastLuckBonus TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                achievements TEXT DEFAULT ''
            )
            """
        )
        
        # Přidání nových sloupců pokud neexistují (pro upgrade existujících databází)
        new_columns = [
            'magicWells INTEGER DEFAULT 0',
            'starForges INTEGER DEFAULT 0', 
            'timeAccelerators INTEGER DEFAULT 0',
            'voidHarvesters INTEGER DEFAULT 0',
            'priceMagicWell INTEGER DEFAULT 500000',
            'priceStarForge INTEGER DEFAULT 5000000',
            'priceTimeAccelerator INTEGER DEFAULT 50000000',
            'priceVoidHarvester INTEGER DEFAULT 1000000000',
            'luckLevel INTEGER DEFAULT 0',
            'mysteryBoxes INTEGER DEFAULT 0',
            'lastLuckBonus TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
            'achievements TEXT DEFAULT \'\''
        ]
        
        for column in new_columns:
            try:
                column_name = column.split()[0]
                cursor.execute(f"ALTER TABLE crystal_game_data ADD COLUMN IF NOT EXISTS {column}")
            except Exception as e:
                print(f"Sloupec {column_name} již existuje nebo chyba: {e}")
        
        # Vytvoření indexů pro výkon
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_crystals ON crystal_game_data(crystals)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_username ON crystal_game_data(username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rebirth ON crystal_game_data(rebirthCount)")
        
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
                lifetime_crystals=%s,
                autoclickers=%s,
                factories=%s,
                mines=%s,
                refineries=%s,
                quantumDrills=%s,
                magicWells=%s,
                starForges=%s,
                timeAccelerators=%s,
                voidHarvesters=%s,
                clickPower=%s,
                totalClicks=%s,
                priceAutoclicker=%s,
                priceFactory=%s,
                priceMine=%s,
                priceRefinery=%s,
                priceQuantumDrill=%s,
                priceMagicWell=%s,
                priceStarForge=%s,
                priceTimeAccelerator=%s,
                priceVoidHarvester=%s,
                priceClickPower=%s,
                rebirthCount=%s,
                rebirthPoints=%s,
                bonusClickPower=%s,
                bonusProduction=%s,
                bonusRebirthPoints=%s,
                luckLevel=%s,
                mysteryBoxes=%s,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
            """,
            (
                gd.get('crystals', 0),
                gd.get('lifetime_crystals', 0),
                gd.get('autoclickers', 0),
                gd.get('factories', 0),
                gd.get('mines', 0),
                gd.get('refineries', 0),
                gd.get('quantumDrills', 0),
                gd.get('magicWells', 0),
                gd.get('starForges', 0),
                gd.get('timeAccelerators', 0),
                gd.get('voidHarvesters', 0),
                gd.get('clickPower', 1),
                gd.get('totalClicks', 0),
                gd.get('priceAutoclicker', 5),
                gd.get('priceFactory', 50),
                gd.get('priceMine', 500),
                gd.get('priceRefinery', 5000),
                gd.get('priceQuantumDrill', 50000),
                gd.get('priceMagicWell', 500000),
                gd.get('priceStarForge', 5000000),
                gd.get('priceTimeAccelerator', 50000000),
                gd.get('priceVoidHarvester', 1000000000),
                gd.get('priceClickPower', 20),
                gd.get('rebirthCount', 0),
                gd.get('rebirthPoints', 0),
                gd.get('bonusClickPower', 0),
                gd.get('bonusProduction', 0),
                gd.get('bonusRebirthPoints', 0),
                gd.get('luckLevel', 0),
                gd.get('mysteryBoxes', 0),
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
            'lifetime_crystals': row.get('lifetime_crystals', 0),
            'autoclickers': row.get('autoclickers', 0),
            'factories': row.get('factories', 0),
            'mines': row.get('mines', 0),
            'refineries': row.get('refineries', 0),
            'quantumDrills': row.get('quantumdrills', 0),
            'magicWells': row.get('magicwells', 0),
            'starForges': row.get('starforges', 0),
            'timeAccelerators': row.get('timeaccelerators', 0),
            'voidHarvesters': row.get('voidharvesters', 0),
            'clickPower': row.get('clickpower', 1),
            'totalClicks': row.get('totalclicks', 0),
            'priceAutoclicker': row.get('priceautoclicker', 5),
            'priceFactory': row.get('pricefactory', 50),
            'priceMine': row.get('pricemine', 500),
            'priceRefinery': row.get('pricerefinery', 5000),
            'priceQuantumDrill': row.get('pricequantumdrill', 50000),
            'priceMagicWell': row.get('pricemagicwell', 500000),
            'priceStarForge': row.get('pricestarforge', 5000000),
            'priceTimeAccelerator': row.get('pricetimeaccelerator', 50000000),
            'priceVoidHarvester': row.get('pricevoidharvester', 1000000000),
            'priceClickPower': row.get('priceclickpower', 20),
            'rebirthCount': row.get('rebirthcount', 0),
            'rebirthPoints': row.get('rebirthpoints', 0),
            'bonusClickPower': row.get('bonusclickpower', 0),
            'bonusProduction': row.get('bonusproduction', 0),
            'bonusRebirthPoints': row.get('bonusrebirthpoints', 0),
            'luckLevel': row.get('lucklevel', 0),
            'mysteryBoxes': row.get('mysteryboxes', 0)
        }

        return jsonify({'success': True, 'game_data': game_data})
    except Exception as e:
        print(f"Chyba načítání: {e}")
        return jsonify({'success': False, 'message': 'Chyba při načítání'}), 500
    finally:
        cursor.close()
        return_db_connection(conn)

# Mystery Box endpoint
@app.route('/open_mystery_box', methods=['POST'])
def open_mystery_box():
    data = request.get_json()
    user_id = data.get('user_id')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Chyba databáze'}), 500
        
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT mysteryBoxes FROM crystal_game_data WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        
        if not row or row['mysteryboxes'] <= 0:
            return jsonify({'success': False, 'message': 'Nemáš žádné mystery boxy!'}), 400
        
        # Náhodné odměny
        rewards = [
            {'type': 'crystals', 'amount': random.randint(1000, 50000), 'name': 'Křišťály'},
            {'type': 'crystals', 'amount': random.randint(10000, 100000), 'name': 'Velké množství křišťálů'},
            {'type': 'click_power', 'amount': random.randint(1, 5), 'name': 'Síla kliku'},
            {'type': 'production_boost', 'amount': random.randint(2, 10), 'name': 'Hodinová produkce'},
        ]
        
        reward = random.choice(rewards)
        
        if reward['type'] == 'crystals':
            cursor.execute(
                "UPDATE crystal_game_data SET crystals = crystals + %s, mysteryBoxes = mysteryBoxes - 1 WHERE id = %s",
                (reward['amount'], user_id)
            )
        elif reward['type'] == 'click_power':
            cursor.execute(
                "UPDATE crystal_game_data SET clickPower = clickPower + %s, mysteryBoxes = mysteryBoxes - 1 WHERE id = %s",
                (reward['amount'], user_id)
            )
        elif reward['type'] == 'production_boost':
            # Dočasný boost - přidáme přímo křišťály jako bonus
            hourly_production = reward['amount'] * 3600  # simulace hodinové produkce
            cursor.execute(
                "UPDATE crystal_game_data SET crystals = crystals + %s, mysteryBoxes = mysteryBoxes - 1 WHERE id = %s",
                (hourly_production, user_id)
            )
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'reward': reward
        })
        
    except Exception as e:
        print(f"Chyba mystery boxu: {e}")
        conn.rollback()
        return jsonify({'success': False, 'message': 'Chyba při otvírání mystery boxu'}), 500
    finally:
        cursor.close()
        return_db_connection(conn)

# Luck bonus endpoint
@app.route('/claim_luck_bonus', methods=['POST'])
def claim_luck_bonus():
    data = request.get_json()
    user_id = data.get('user_id')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Chyba databáze'}), 500
        
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT luckLevel, lastLuckBonus FROM crystal_game_data WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        
        if not row:
            return jsonify({'success': False, 'message': 'Hráč nenalezen'}), 404
        
        # Kontrola, zda už dnes získal bonus
        import datetime
        last_bonus = row.get('lastluckbonus')
        now = datetime.datetime.now()
        
        if last_bonus and (now - last_bonus).total_seconds() < 3600:  # 1 hodina cooldown
            remaining = 3600 - (now - last_bonus).total_seconds()
            return jsonify({
                'success': False, 
                'message': f'Luck bonus bude dostupný za {int(remaining/60)} minut!'
            }), 400
        
        luck_level = row.get('lucklevel', 0)
        if luck_level <= 0:
            return jsonify({'success': False, 'message': 'Nemáš žádné luck levely!'}), 400
        
        # Výpočet bonusu (čím vyšší level, tím větší bonus)
        base_bonus = random.randint(100, 1000)
        luck_multiplier = 1 + (luck_level * 0.5)  # každý level +50% bonusu
        total_bonus = int(base_bonus * luck_multiplier)
        
        # Šance na mystery box (5% * luck level)
        mystery_box_chance = min(luck_level * 5, 50)  # max 50%
        got_mystery_box = random.randint(1, 100) <= mystery_box_chance
        
        if got_mystery_box:
            cursor.execute(
                """UPDATE crystal_game_data SET 
                   crystals = crystals + %s, 
                   mysteryBoxes = mysteryBoxes + 1,
                   lastLuckBonus = CURRENT_TIMESTAMP 
                   WHERE id = %s""",
                (total_bonus, user_id)
            )
        else:
            cursor.execute(
                """UPDATE crystal_game_data SET 
                   crystals = crystals + %s, 
                   lastLuckBonus = CURRENT_TIMESTAMP 
                   WHERE id = %s""",
                (total_bonus, user_id)
            )
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'bonus': total_bonus,
            'got_mystery_box': got_mystery_box
        })
        
    except Exception as e:
        print(f"Chyba luck bonusu: {e}")
        conn.rollback()
        return jsonify({'success': False, 'message': 'Chyba při získávání luck bonusu'}), 500
    finally:
        cursor.close()
        return_db_connection(conn)

# Rebirth endpoint
@app.route('/rebirth', methods=['POST'])
def rebirth():
    data = request.get_json()
    user_id = data.get('user_id')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Chyba databáze'}), 500
        
    cursor = conn.cursor()
    
    try:
        # Načtení aktuálních dat hráče
        cursor.execute("SELECT * FROM crystal_game_data WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        
        if not row:
            return jsonify({'success': False, 'message': 'Hráč nenalezen'}), 404
        
        current_crystals = row.get('crystals', 0)
        rebirth_count = row.get('rebirthcount', 0)
        
        # Výpočet potřebných křišťálů pro rebirth
        required_crystals = 100000 * (2 ** rebirth_count)
        
        if current_crystals < required_crystals:
            return jsonify({
                'success': False, 
                'message': f'Potřebuješ alespoň {required_crystals:,} křišťálů pro rebirth!'
            }), 400
        
        # Výpočet rebirth points
        rebirth_points = math.floor(math.log10(current_crystals) * (1 + row.get('bonusrebirthpoints', 0)/100))
        
        # Šance na luck level (10% za rebirth)
        luck_gained = 0
        if random.randint(1, 100) <= 10:  # 10% šance
            luck_gained = 1

        # Reset hráče + přidání bonusů
        cursor.execute(
            """
            UPDATE crystal_game_data SET
                crystals=0,
                autoclickers=0,
                factories=0,
                mines=0,
                refineries=0,
                quantumDrills=0,
                magicWells=0,
                starForges=0,
                timeAccelerators=0,
                voidHarvesters=0,
                clickPower=1,
                priceAutoclicker=5,
                priceFactory=50,
                priceMine=500,
                priceRefinery=5000,
                priceQuantumDrill=50000,
                priceMagicWell=500000,
                priceStarForge=5000000,
                priceTimeAccelerator=50000000,
                priceVoidHarvester=1000000000,
                priceClickPower=20,
                rebirthCount=rebirthCount + 1,
                rebirthPoints=rebirthPoints + %s,
                luckLevel=luckLevel + %s,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
            RETURNING rebirthCount, rebirthPoints, luckLevel
            """,
            (rebirth_points, luck_gained, user_id)
        )
        
        result = cursor.fetchone()
        conn.commit()
        
        return jsonify({
            'success': True,
            'rebirthCount': result['rebirthcount'],
            'rebirthPoints': result['rebirthpoints'],
            'luckLevel': result['lucklevel'],
            'gainedPoints': rebirth_points,
            'luckGained': luck_gained
        })
    except Exception as e:
        print(f"Chyba rebirthu: {e}")
        conn.rollback()
        return jsonify({'success': False, 'message': 'Chyba při rebirthu'}), 500
    finally:
        cursor.close()
        return_db_connection(conn)

# Upgrade rebirth bonusů
@app.route('/upgrade_rebirth', methods=['POST'])
def upgrade_rebirth():
    data = request.get_json()
    user_id = data.get('user_id')
    bonus_type = data.get('type')  # 'click' nebo 'production' nebo 'points'
    
    if bonus_type not in ['click', 'production', 'points']:
        return jsonify({'success': False, 'message': 'Neplatný typ bonusu'}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Chyba databáze'}), 500
        
    cursor = conn.cursor()
    
    try:
        # Načtení aktuálních dat hráče
        cursor.execute("SELECT rebirthPoints FROM crystal_game_data WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        
        if not row:
            return jsonify({'success': False, 'message': 'Hráč nenalezen'}), 404
        
        current_points = row['rebirthpoints']
        cost = 10  # Základní cena upgradu
        
        if current_points < cost:
            return jsonify({
                'success': False, 
                'message': f'Potřebuješ alespoň {cost} rebirth bodů pro upgrade!'
            }), 400
        
        # Aktualizace příslušného bonusu
        if bonus_type == 'click':
            update_field = 'bonusClickPower'
        elif bonus_type == 'production':
            update_field = 'bonusProduction'
        else:  # points
            update_field = 'bonusRebirthPoints'
        
        cursor.execute(
            f"""
            UPDATE crystal_game_data SET
                {update_field}={update_field} + 1,
                rebirthPoints=rebirthPoints - %s,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
            RETURNING {update_field}, rebirthPoints
            """,
            (cost, user_id)
        )
        
        result = cursor.fetchone()
        conn.commit()
        
        return jsonify({
            'success': True,
            'newValue': result[update_field.lower()],
            'remainingPoints': result['rebirthpoints']
        })
    except Exception as e:
        print(f"Chyba upgradu rebirth bonusu: {e}")
        conn.rollback()
        return jsonify({'success': False, 'message': 'Chyba při upgradu'}), 500
    finally:
        cursor.close()
        return_db_connection(conn)

# Endpoint pro žebříček - OPRAVENÁ CPS kalkulace
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
            # OPRAVENÁ CPS kalkulace
            query = """
            SELECT username, 
                   (COALESCE(autoclickers, 0) * 1 + 
                    COALESCE(factories, 0) * 5 + 
                    COALESCE(mines, 0) * 50 + 
                    COALESCE(refineries, 0) * 200 + 
                    COALESCE(quantumDrills, 0) * 1000 +
                    COALESCE(magicWells, 0) * 5000 +
                    COALESCE(starForges, 0) * 25000 +
                    COALESCE(timeAccelerators, 0) * 100000 +
                    COALESCE(voidHarvesters, 0) * 500000) as value
            FROM crystal_game_data 
            WHERE (COALESCE(autoclickers, 0) * 1 + 
                  COALESCE(factories, 0) * 5 + 
                  COALESCE(mines, 0) * 50 + 
                  COALESCE(refineries, 0) * 200 + 
                  COALESCE(quantumDrills, 0) * 1000 +
                  COALESCE(magicWells, 0) * 5000 +
                  COALESCE(starForges, 0) * 25000 +
                  COALESCE(timeAccelerators, 0) * 100000 +
                  COALESCE(voidHarvesters, 0) * 500000) > 0
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
                   (COALESCE(autoclickers, 0) + COALESCE(factories, 0) + COALESCE(mines, 0) + 
                    COALESCE(refineries, 0) + COALESCE(quantumDrills, 0) + COALESCE(magicWells, 0) +
                    COALESCE(starForges, 0) + COALESCE(timeAccelerators, 0) + COALESCE(voidHarvesters, 0)) as value
            FROM crystal_game_data 
            WHERE (COALESCE(autoclickers, 0) + COALESCE(factories, 0) + COALESCE(mines, 0) + 
                  COALESCE(refineries, 0) + COALESCE(quantumDrills, 0) + COALESCE(magicWells, 0) +
                  COALESCE(starForges, 0) + COALESCE(timeAccelerators, 0) + COALESCE(voidHarvesters, 0)) > 0
            ORDER BY value DESC 
            LIMIT 10
            """
            label = "Celkové budovy"
        elif leaderboard_type == 'rebirth':
            query = """
            SELECT username, COALESCE(rebirthCount, 0) as value 
            FROM crystal_game_data 
            WHERE COALESCE(rebirthCount, 0) > 0 
            ORDER BY COALESCE(rebirthCount, 0) DESC 
            LIMIT 10
            """
            label = "Rebirthy"
        elif leaderboard_type == 'luck':
            query = """
            SELECT username, COALESCE(luckLevel, 0) as value 
            FROM crystal_game_data 
            WHERE COALESCE(luckLevel, 0) > 0 
            ORDER BY COALESCE(luckLevel, 0) DESC 
            LIMIT 10
            """
            label = "Luck Level"
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
        
        cursor.execute("SELECT SUM(rebirthCount) as total_rebirths FROM crystal_game_data")
        total_rebirths = cursor.fetchone()['total_rebirths'] or 0
        
        cursor.execute("SELECT SUM(mysteryBoxes) as total_mystery_boxes FROM crystal_game_data")
        total_mystery_boxes = cursor.fetchone()['total_mystery_boxes'] or 0
        
        return jsonify({
            'success': True,
            'stats': {
                'total_players': total_players,
                'total_crystals': total_crystals,
                'total_clicks': total_clicks,
                'total_rebirths': total_rebirths,
                'total_mystery_boxes': total_mystery_boxes
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
