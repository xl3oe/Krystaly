from flask import Flask, request, jsonify, send_from_directory
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool
from flask_cors import CORS
import math
import random
import time
from datetime import datetime, timedelta
import logging

# Nastavení logování
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# Konfigurace databáze - PostgreSQL pro Render
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    # Fallback pro lokální vývoj
    DATABASE_URL = "postgresql://localhost/crystal_game"

# Pokud je DATABASE_URL od Heroku/Render, může obsahovat postgres:// místo postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

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
        logger.info("Connection pool vytvořen úspěšně")
    except Exception as e:
        logger.error(f"Chyba při vytváření connection poolu: {e}")
        connection_pool = None

def get_db_connection():
    """Získá připojení z poolu"""
    global connection_pool
    if connection_pool:
        try:
            return connection_pool.getconn()
        except Exception as e:
            logger.error(f"Chyba při získávání připojení z poolu: {e}")
    
    # Fallback - přímé připojení
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        logger.error(f"Chyba při přímém připojení: {e}")
        return None

def return_db_connection(conn):
    """Vrátí připojení zpět do poolu"""
    global connection_pool
    if connection_pool and conn:
        try:
            connection_pool.putconn(conn)
        except Exception as e:
            logger.error(f"Chyba při vracení připojení: {e}")
            try:
                conn.close()
            except:
                pass
    elif conn:
        try:
            conn.close()
        except:
            pass

# Zajištění, že tabulka existuje
def init_database():
    conn = get_db_connection()
    if not conn:
        logger.error("Nelze se připojit k databázi!")
        return
        
    cursor = conn.cursor()
    try:
        # Vytvoření tabulky pro PostgreSQL s novými položkami
        cursor.execute("""
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
                quantumdrills INTEGER DEFAULT 0,
                supertokens INTEGER DEFAULT 0,
                magicwells INTEGER DEFAULT 0,
                starforges INTEGER DEFAULT 0,
                timeaccelerators INTEGER DEFAULT 0,
                voidharvesters INTEGER DEFAULT 0,
                clickpower INTEGER DEFAULT 1,
                totalclicks INTEGER DEFAULT 0,
                priceautoclicker BIGINT DEFAULT 5,
                pricefactory BIGINT DEFAULT 50,
                pricemine BIGINT DEFAULT 500,
                pricerefinery BIGINT DEFAULT 5000,
                pricequantumdrill BIGINT DEFAULT 50000,
                pricemagicwell BIGINT DEFAULT 500000,
                pricestarforge BIGINT DEFAULT 5000000,
                pricetimeaccelerator BIGINT DEFAULT 50000000,
                pricevoidharvester BIGINT DEFAULT 1000000000,
                priceclickpower BIGINT DEFAULT 20,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                rebirthcount INTEGER DEFAULT 0,
                rebirthpoints INTEGER DEFAULT 0,
                bonusclickpower INTEGER DEFAULT 0,
                bonusproduction INTEGER DEFAULT 0,
                bonusrebirthpoints INTEGER DEFAULT 0,
                lucklevel INTEGER DEFAULT 0,
                mysteryboxes INTEGER DEFAULT 0,
                lastluckbonus TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '2 hours',
                achievements TEXT DEFAULT ''
            )
        """)
        
        # Přidání nových sloupců pokud neexistují (pro upgrade existujících databází)
        new_columns = [
            ('magicwells', 'INTEGER DEFAULT 0'),
            ('starforges', 'INTEGER DEFAULT 0'), 
            ('timeaccelerators', 'INTEGER DEFAULT 0'),
            ('voidharvesters', 'INTEGER DEFAULT 0'),
            ('pricemagicwell', 'BIGINT DEFAULT 500000'),
            ('pricestarforge', 'BIGINT DEFAULT 5000000'),
            ('pricetimeaccelerator', 'BIGINT DEFAULT 50000000'),
            ('pricevoidharvester', 'BIGINT DEFAULT 1000000000'),
            ('lucklevel', 'INTEGER DEFAULT 0'),
            ('mysteryboxes', 'INTEGER DEFAULT 0'),
            ('lastluckbonus', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL \'2 hours\''),
            ('achievements', 'TEXT DEFAULT \'\'')
        ]
        
        for column_name, column_def in new_columns:
            try:
                cursor.execute(f"ALTER TABLE crystal_game_data ADD COLUMN IF NOT EXISTS {column_name} {column_def}")
            except Exception as e:
                logger.info(f"Sloupec {column_name} již existuje nebo chyba: {e}")
        
        # Vytvoření indexů pro výkon
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_crystals ON crystal_game_data(crystals)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_username ON crystal_game_data(username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rebirth ON crystal_game_data(rebirthcount)")
        
        conn.commit()
        logger.info("Databáze inicializována úspěšně")
    except Exception as e:
        logger.error(f"Chyba při inicializaci databáze: {e}")
        conn.rollback()
    finally:
        cursor.close()
        return_db_connection(conn)

# Error handler
@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"Neočekávaná chyba: {str(e)}", exc_info=True)
    return jsonify({'success': False, 'message': 'Interní chyba serveru'}), 500

# Posílání hlavní stránky
@app.route('/')
def index():
    try:
        return send_from_directory(app.static_folder, 'index.html')
    except Exception as e:
        logger.error(f"Chyba při načítání index.html: {e}")
        return jsonify({'success': False, 'message': 'Chyba při načítání stránky'}), 500

# Health check pro Render
@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()}), 200

# Registrace
@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Chybí data'}), 400
            
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
            logger.error(f"Chyba registrace: {e}")
            conn.rollback()
            return jsonify({'success': False, 'message': 'Chyba při registraci'}), 500
        finally:
            cursor.close()
            return_db_connection(conn)
    except Exception as e:
        logger.error(f"Chyba v registraci: {e}")
        return jsonify({'success': False, 'message': 'Chyba serveru'}), 500

# Přihlášení
@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Chybí data'}), 400
            
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
            logger.error(f"Chyba přihlášení: {e}")
            return jsonify({'success': False, 'message': 'Chyba při přihlašování'}), 500
        finally:
            cursor.close()
            return_db_connection(conn)
    except Exception as e:
        logger.error(f"Chyba v přihlášení: {e}")
        return jsonify({'success': False, 'message': 'Chyba serveru'}), 500

# Uložení hry
@app.route('/save_game', methods=['POST'])
def save_game():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Chybí data'}), 400
            
        user_id = data.get('user_id')
        gd = data.get('game_data', {})

        if not user_id:
            return jsonify({'success': False, 'message': 'Chybí user_id'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Chyba databáze'}), 500
            
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE crystal_game_data SET
                    crystals=%s,
                    lifetime_crystals=%s,
                    autoclickers=%s,
                    factories=%s,
                    mines=%s,
                    refineries=%s,
                    quantumdrills=%s,
                    magicwells=%s,
                    starforges=%s,
                    timeaccelerators=%s,
                    voidharvesters=%s,
                    clickpower=%s,
                    totalclicks=%s,
                    priceautoclicker=%s,
                    pricefactory=%s,
                    pricemine=%s,
                    pricerefinery=%s,
                    pricequantumdrill=%s,
                    pricemagicwell=%s,
                    pricestarforge=%s,
                    pricetimeaccelerator=%s,
                    pricevoidharvester=%s,
                    priceclickpower=%s,
                    rebirthcount=%s,
                    rebirthpoints=%s,
                    bonusclickpower=%s,
                    bonusproduction=%s,
                    bonusrebirthpoints=%s,
                    lucklevel=%s,
                    mysteryboxes=%s,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=%s
            """, (
                int(gd.get('crystals', 0)),
                int(gd.get('lifetime_crystals', 0)),
                int(gd.get('autoclickers', 0)),
                int(gd.get('factories', 0)),
                int(gd.get('mines', 0)),
                int(gd.get('refineries', 0)),
                int(gd.get('quantumDrills', 0)),
                int(gd.get('magicWells', 0)),
                int(gd.get('starForges', 0)),
                int(gd.get('timeAccelerators', 0)),
                int(gd.get('voidHarvesters', 0)),
                int(gd.get('clickPower', 1)),
                int(gd.get('totalClicks', 0)),
                int(gd.get('priceAutoclicker', 5)),
                int(gd.get('priceFactory', 50)),
                int(gd.get('priceMine', 500)),
                int(gd.get('priceRefinery', 5000)),
                int(gd.get('priceQuantumDrill', 50000)),
                int(gd.get('priceMagicWell', 500000)),
                int(gd.get('priceStarForge', 5000000)),
                int(gd.get('priceTimeAccelerator', 50000000)),
                int(gd.get('priceVoidHarvester', 1000000000)),
                int(gd.get('priceClickPower', 20)),
                int(gd.get('rebirthCount', 0)),
                int(gd.get('rebirthPoints', 0)),
                int(gd.get('bonusClickPower', 0)),
                int(gd.get('bonusProduction', 0)),
                int(gd.get('bonusRebirthPoints', 0)),
                int(gd.get('luckLevel', 0)),
                int(gd.get('mysteryBoxes', 0)),
                user_id
            ))
            conn.commit()
            return jsonify({'success': True})
        except Exception as e:
            logger.error(f"Chyba ukládání: {e}")
            conn.rollback()
            return jsonify({'success': False, 'message': 'Chyba při ukládání'}), 500
        finally:
            cursor.close()
            return_db_connection(conn)
    except Exception as e:
        logger.error(f"Chyba v ukládání hry: {e}")
        return jsonify({'success': False, 'message': 'Chyba serveru'}), 500

# Načtení hry
@app.route('/load_game')
def load_game():
    try:
        user_id = request.args.get('user_id')
        
        if not user_id:
            return jsonify({'success': False, 'message': 'Chybí user_id'}), 400
        
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
                'crystals': int(row.get('crystals') or 0),
                'lifetime_crystals': int(row.get('lifetime_crystals') or 0),
                'autoclickers': int(row.get('autoclickers') or 0),
                'factories': int(row.get('factories') or 0),
                'mines': int(row.get('mines') or 0),
                'refineries': int(row.get('refineries') or 0),
                'quantumDrills': int(row.get('quantumdrills') or 0),
                'magicWells': int(row.get('magicwells') or 0),
                'starForges': int(row.get('starforges') or 0),
                'timeAccelerators': int(row.get('timeaccelerators') or 0),
                'voidHarvesters': int(row.get('voidharvesters') or 0),
                'clickPower': int(row.get('clickpower') or 1),
                'totalClicks': int(row.get('totalclicks') or 0),
                'priceAutoclicker': int(row.get('priceautoclicker') or 5),
                'priceFactory': int(row.get('pricefactory') or 50),
                'priceMine': int(row.get('pricemine') or 500),
                'priceRefinery': int(row.get('pricerefinery') or 5000),
                'priceQuantumDrill': int(row.get('pricequantumdrill') or 50000),
                'priceMagicWell': int(row.get('pricemagicwell') or 500000),
                'priceStarForge': int(row.get('pricestarforge') or 5000000),
                'priceTimeAccelerator': int(row.get('pricetimeaccelerator') or 50000000),
                'priceVoidHarvester': int(row.get('pricevoidharvester') or 1000000000),
                'priceClickPower': int(row.get('priceclickpower') or 20),
                'rebirthCount': int(row.get('rebirthcount') or 0),
                'rebirthPoints': int(row.get('rebirthpoints') or 0),
                'bonusClickPower': int(row.get('bonusclickpower') or 0),
                'bonusProduction': int(row.get('bonusproduction') or 0),
                'bonusRebirthPoints': int(row.get('bonusrebirthpoints') or 0),
                'luckLevel': int(row.get('lucklevel') or 0),
                'mysteryBoxes': int(row.get('mysteryboxes') or 0),
                'lastLuckBonus': row.get('lastluckbonus')
            }

            return jsonify({'success': True, 'game_data': game_data})
        except Exception as e:
            logger.error(f"Chyba načítání: {e}")
            return jsonify({'success': False, 'message': 'Chyba při načítání'}), 500
        finally:
            cursor.close()
            return_db_connection(conn)
    except Exception as e:
        logger.error(f"Chyba v načítání hry: {e}")
        return jsonify({'success': False, 'message': 'Chyba serveru'}), 500

# Mystery Box endpoint
@app.route('/open_mystery_box', methods=['POST'])
def open_mystery_box():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Chybí data'}), 400
            
        user_id = data.get('user_id')
        
        if not user_id:
            return jsonify({'success': False, 'message': 'Chybí user_id'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Chyba databáze'}), 500
            
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT mysteryboxes FROM crystal_game_data WHERE id = %s", (user_id,))
            row = cursor.fetchone()
            
            if not row or (row['mysteryboxes'] or 0) <= 0:
                return jsonify({'success': False, 'message': 'Nemáš žádné mystery boxy!'}), 400
            
            # Náhodné odměny
            rewards = [
                {'type': 'crystals', 'amount': random.randint(1000, 50000), 'name': 'Křišťály'},
                {'type': 'crystals', 'amount': random.randint(10000, 100000), 'name': 'Velké množství křišťálů'},
                {'type': 'click_power', 'amount': random.randint(1, 5), 'name': 'Síla kliku'},
                {'type': 'production_boost', 'amount': random.randint(50000, 200000), 'name': 'Produkční boost'},
            ]
            
            reward = random.choice(rewards)
            
            if reward['type'] == 'crystals' or reward['type'] == 'production_boost':
                cursor.execute(
                    "UPDATE crystal_game_data SET crystals = crystals + %s, mysteryboxes = mysteryboxes - 1 WHERE id = %s",
                    (reward['amount'], user_id)
                )
            elif reward['type'] == 'click_power':
                cursor.execute(
                    "UPDATE crystal_game_data SET clickpower = clickpower + %s, mysteryboxes = mysteryboxes - 1 WHERE id = %s",
                    (reward['amount'], user_id)
                )
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'reward': reward
            })
            
        except Exception as e:
            logger.error(f"Chyba mystery boxu: {e}")
            conn.rollback()
            return jsonify({'success': False, 'message': 'Chyba při otvírání mystery boxu'}), 500
        finally:
            cursor.close()
            return_db_connection(conn)
    except Exception as e:
        logger.error(f"Chyba v mystery box: {e}")
        return jsonify({'success': False, 'message': 'Chyba serveru'}), 500

# Luck bonus endpoint
@app.route('/claim_luck_bonus', methods=['POST'])
def claim_luck_bonus():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Chybí data'}), 400
            
        user_id = data.get('user_id')
        
        if not user_id:
            return jsonify({'success': False, 'message': 'Chybí user_id'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Chyba databáze'}), 500
            
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT lucklevel, lastluckbonus FROM crystal_game_data WHERE id = %s", (user_id,))
            row = cursor.fetchone()
            
            if not row:
                return jsonify({'success': False, 'message': 'Hráč nenalezen'}), 404
            
            # Kontrola cooldownu - 1 hodina
            last_bonus = row.get('lastluckbonus')
            now = datetime.now()
            
            if last_bonus:
                time_diff = now - last_bonus
                if time_diff.total_seconds() < 3600:  # 1 hodina cooldown
                    remaining = 3600 - time_diff.total_seconds()
                    return jsonify({
                        'success': False, 
                        'message': f'Luck bonus bude dostupný za {int(remaining/60)} minut!'
                    }), 400
            
            luck_level = int(row.get('lucklevel') or 0)
            if luck_level <= 0:
                return jsonify({'success': False, 'message': 'Nemáš žádné luck levely!'}), 400
            
            # Výpočet bonusu (čím vyšší level, tím větší bonus)
            base_bonus = random.randint(100, 1000)
            luck_multiplier = 1 + (luck_level * 0.5)  # každý level +50% bonusu
            total_bonus = int(base_bonus * luck_multiplier)
            
            # Šance na mystery box (5% * luck level, max 50%)
            mystery_box_chance = min(luck_level * 5, 50)
            got_mystery_box = random.randint(1, 100) <= mystery_box_chance
            
            if got_mystery_box:
                cursor.execute("""
                    UPDATE crystal_game_data SET 
                    crystals = crystals + %s, 
                    mysteryboxes = mysteryboxes + 1,
                    lastluckbonus = CURRENT_TIMESTAMP 
                    WHERE id = %s
                """, (total_bonus, user_id))
            else:
                cursor.execute("""
                    UPDATE crystal_game_data SET 
                    crystals = crystals + %s, 
                    lastluckbonus = CURRENT_TIMESTAMP 
                    WHERE id = %s
                """, (total_bonus, user_id))
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'bonus': total_bonus,
                'got_mystery_box': got_mystery_box
            })
            
        except Exception as e:
            logger.error(f"Chyba luck bonusu: {e}")
            conn.rollback()
            return jsonify({'success': False, 'message': 'Chyba při získávání luck bonusu'}), 500
        finally:
            cursor.close()
            return_db_connection(conn)
    except Exception as e:
        logger.error(f"Chyba v luck bonus: {e}")
        return jsonify({'success': False, 'message': 'Chyba serveru'}), 500

# Rebirth endpoint
@app.route('/rebirth', methods=['POST'])
def rebirth():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Chybí data'}), 400
            
        user_id = data.get('user_id')
        
        if not user_id:
            return jsonify({'success': False, 'message': 'Chybí user_id'}), 400
        
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
            
            current_crystals = int(row.get('crystals') or 0)
            rebirth_count = int(row.get('rebirthcount') or 0)
            bonus_rebirth_points = int(row.get('bonusrebirthpoints') or 0)
            
            # Výpočet potřebných křišťálů pro rebirth
            required_crystals = 100000 * (2 ** rebirth_count)
            
            if current_crystals < required_crystals:
                return jsonify({
                    'success': False, 
                    'message': f'Potřebuješ alespoň {required_crystals:,} křišťálů pro rebirth!'
                }), 400
            
            # Výpočet rebirth points
            if current_crystals > 0:
                rebirth_points = max(
    1, 
    math.floor((math.log10(current_crystals) + current_crystals / 1_000_000) * (1 + bonus_rebirth_points/100))
)

            else:
                rebirth_points = 1
            
            # Šance na luck level (10% za rebirth)
            luck_gained = 1 if random.randint(1, 100) <= 35 else 0

            # Reset hráče + přidání bonusů
            cursor.execute("""
                UPDATE crystal_game_data SET
                    crystals=0,
                    autoclickers=0,
                    factories=0,
                    mines=0,
                    refineries=0,
                    quantumdrills=0,
                    magicwells=0,
                    starforges=0,
                    timeaccelerators=0,
                    voidharvesters=0,
                    clickpower=1,
                    priceautoclicker=5,
                    pricefactory=50,
                    pricemine=500,
                    pricerefinery=5000,
                    pricequantumdrill=50000,
                    pricemagicwell=500000,
                    pricestarforge=5000000,
                    pricetimeaccelerator=50000000,
                    pricevoidharvester=1000000000,
                    priceclickpower=20,
                    rebirthcount=rebirthcount + 1,
                    rebirthpoints=rebirthpoints + %s,
                    lucklevel=lucklevel + %s,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=%s
                RETURNING rebirthcount, rebirthpoints, lucklevel
            """, (rebirth_points, luck_gained, user_id))
            
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
            logger.error(f"Chyba rebirthu: {e}")
            conn.rollback()
            return jsonify({'success': False, 'message': 'Chyba při rebirthu'}), 500
        finally:
            cursor.close()
            return_db_connection(conn)
    except Exception as e:
        logger.error(f"Chyba v rebirth: {e}")
        return jsonify({'success': False, 'message': 'Chyba serveru'}), 500


# Upgrade rebirth bonusů
@app.route('/upgrade_rebirth', methods=['POST'])
def upgrade_rebirth():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Chybí data'}), 400
            
        user_id = data.get('user_id')
        bonus_type = data.get('type')  # 'click' nebo 'production' nebo 'points'
        
        if not user_id:
            return jsonify({'success': False, 'message': 'Chybí user_id'}), 400
        
        if bonus_type not in ['click', 'production', 'points']:
            return jsonify({'success': False, 'message': 'Neplatný typ bonusu'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Chyba databáze'}), 500
            
        cursor = conn.cursor()
        
        try:
            # Načtení aktuálních dat hráče
            cursor.execute("SELECT rebirthpoints FROM crystal_game_data WHERE id = %s", (user_id,))
            row = cursor.fetchone()
            
            if not row:
                return jsonify({'success': False, 'message': 'Hráč nenalezen'}), 404
            
            current_points = int(row['rebirthpoints'] or 0)
            cost = 10  # Základní cena upgradu
            
            if current_points < cost:
                return jsonify({
                    'success': False, 
                    'message': f'Potřebuješ alespoň {cost} rebirth bodů pro upgrade!'
                }), 400
            
            # Aktualizace příslušného bonusu
            if bonus_type == 'click':
                update_field = 'bonusclickpower'
            elif bonus_type == 'production':
                update_field = 'bonusproduction'
            else: #points
                update_field = "bonusrebirthpoints"
            
            cursor.execute(f"""
                UPDATE crystal_game_data SET
                    {update_field}={update_field} + 100,
                    rebirthpoints=rebirthpoints - %s,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=%s
                RETURNING {update_field}, rebirthpoints
            """, (cost, user_id))
            
            result = cursor.fetchone()
            conn.commit()
            
            return jsonify({
                'success': True,
                'newValue': result[update_field],
                'remainingPoints': result['rebirthpoints']
            })
        except Exception as e:
            logger.error(f"Chyba upgradu rebirth bonusu: {e}")
            conn.rollback()
            return jsonify({'success': False, 'message': 'Chyba při upgradu'}), 500
        finally:
            cursor.close()
            return_db_connection(conn)
    except Exception as e:
        logger.error(f"Chyba v upgrade rebirth: {e}")
        return jsonify({'success': False, 'message': 'Chyba serveru'}), 500

# Endpoint pro žebříček
@app.route('/leaderboard')
def leaderboard():
    try:
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
                # CPS kalkulace
                query = """
                SELECT username, 
                       (COALESCE(autoclickers, 0) * 1 + 
                        COALESCE(factories, 0) * 5 + 
                        COALESCE(mines, 0) * 50 + 
                        COALESCE(refineries, 0) * 200 + 
                        COALESCE(quantumdrills, 0) * 1000 +
                        COALESCE(magicwells, 0) * 5000 +
                        COALESCE(starforges, 0) * 25000 +
                        COALESCE(timeaccelerators, 0) * 100000 +
                        COALESCE(voidharvesters, 0) * 500000) as value
                FROM crystal_game_data 
                WHERE (COALESCE(autoclickers, 0) * 1 + 
                      COALESCE(factories, 0) * 5 + 
                      COALESCE(mines, 0) * 50 + 
                      COALESCE(refineries, 0) * 200 + 
                      COALESCE(quantumdrills, 0) * 1000 +
                      COALESCE(magicwells, 0) * 5000 +
                      COALESCE(starforges, 0) * 25000 +
                      COALESCE(timeaccelerators, 0) * 100000 +
                      COALESCE(voidharvesters, 0) * 500000) > 0
                ORDER BY value DESC 
                LIMIT 10
                """
                label = "CPS"
            elif leaderboard_type == 'clicks':
                query = """
                SELECT username, COALESCE(totalclicks, 0) as value 
                FROM crystal_game_data 
                WHERE COALESCE(totalclicks, 0) > 0 
                ORDER BY COALESCE(totalclicks, 0) DESC 
                LIMIT 10
                """
                label = "Celkové kliky"
            elif leaderboard_type == 'buildings':
                query = """
                SELECT username, 
                       (COALESCE(autoclickers, 0) + COALESCE(factories, 0) + COALESCE(mines, 0) + 
                        COALESCE(refineries, 0) + COALESCE(quantumdrills, 0) + COALESCE(magicwells, 0) +
                        COALESCE(starforges, 0) + COALESCE(timeaccelerators, 0) + COALESCE(voidharvesters, 0)) as value
                FROM crystal_game_data 
                WHERE (COALESCE(autoclickers, 0) + COALESCE(factories, 0) + COALESCE(mines, 0) + 
                      COALESCE(refineries, 0) + COALESCE(quantumdrills, 0) + COALESCE(magicwells, 0) +
                      COALESCE(starforges, 0) + COALESCE(timeaccelerators, 0) + COALESCE(voidharvesters, 0)) > 0
                ORDER BY value DESC 
                LIMIT 10
                """
                label = "Celkové budovy"
            elif leaderboard_type == 'rebirth':
                query = """
                SELECT username, COALESCE(rebirthcount, 0) as value 
                FROM crystal_game_data 
                WHERE COALESCE(rebirthcount, 0) > 0 
                ORDER BY COALESCE(rebirthcount, 0) DESC 
                LIMIT 10
                """
                label = "Rebirthy"
            elif leaderboard_type == 'luck':
                query = """
                SELECT username, COALESCE(lucklevel, 0) as value 
                FROM crystal_game_data 
                WHERE COALESCE(lucklevel, 0) > 0 
                ORDER BY COALESCE(lucklevel, 0) DESC 
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
            logger.error(f"Chyba žebříčku: {e}")
            return jsonify({'success': False, 'message': 'Chyba při načítání žebříčku'}), 500
        finally:
            cursor.close()
            return_db_connection(conn)
    except Exception as e:
        logger.error(f"Chyba v leaderboard: {e}")
        return jsonify({'success': False, 'message': 'Chyba serveru'}), 500

# Statistiky pro admina
@app.route('/stats')
def stats():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Chyba databáze'}), 500
            
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) as total_players FROM crystal_game_data")
            total_players = cursor.fetchone()['total_players']
            
            cursor.execute("SELECT COALESCE(SUM(crystals), 0) as total_crystals FROM crystal_game_data")
            total_crystals = cursor.fetchone()['total_crystals'] or 0
            
            cursor.execute("SELECT COALESCE(SUM(totalclicks), 0) as total_clicks FROM crystal_game_data")
            total_clicks = cursor.fetchone()['total_clicks'] or 0
            
            cursor.execute("SELECT COALESCE(SUM(rebirthcount), 0) as total_rebirths FROM crystal_game_data")
            total_rebirths = cursor.fetchone()['total_rebirths'] or 0
            
            cursor.execute("SELECT COALESCE(SUM(mysteryboxes), 0) as total_mystery_boxes FROM crystal_game_data")
            total_mystery_boxes = cursor.fetchone()['total_mystery_boxes'] or 0
            
            return jsonify({
                'success': True,
                'stats': {
                    'total_players': int(total_players),
                    'total_crystals': int(total_crystals),
                    'total_clicks': int(total_clicks),
                    'total_rebirths': int(total_rebirths),
                    'total_mystery_boxes': int(total_mystery_boxes)
                }
            })
        except Exception as e:
            logger.error(f"Chyba statistik: {e}")
            return jsonify({'success': False, 'message': 'Chyba při načítání statistik'}), 500
        finally:
            cursor.close()
            return_db_connection(conn)
    except Exception as e:
        logger.error(f"Chyba ve statistikách: {e}")
        return jsonify({'success': False, 'message': 'Chyba serveru'}), 500

# Graceful shutdown
import signal
import sys

def signal_handler(sig, frame):
    logger.info('Ukončuji server...')
    if connection_pool:
        try:
            connection_pool.closeall()
            logger.info('Connection pool uzavřen')
        except Exception as e:
            logger.error(f"Chyba při uzavírání connection poolu: {e}")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Inicializace při startu
try:
    init_connection_pool()
    init_database()
    logger.info("Server úspěšně inicializován")
except Exception as e:
    logger.error(f"Chyba při inicializaci serveru: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    logger.info(f"Spouštím server na portu {port}, debug={debug_mode}")
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
