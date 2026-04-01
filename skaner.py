import requests 
import sqlite3
import re

URL = "https://www.biznesradar.pl/skaner-akcji-get-json/"
headers1 = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",   # Podszywanie się sieciowe w celu ominięcia blokady przeciw botom 
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": "cookiedisc=1; _bruid=9c065c24f33a0e1e6ad3abb2d4bb7752; var_p_agg=1d; PHPSESSID=96kntb269h3umhsc7jul863va5; ca=; var_fbh=100"
    
    }
PAYLOAD = {
    "Market[id]": "Market",
    "Market[values][]": ["GPW", "NC"],
    "RealMarketCap[id]": "RealMarketCap",
    "RealMarketCap[from]": "20000000",
    "RealMarketCap[to]": "150000000",
    "RCG[id]": "RCG",
    "RCG[from]": "0",
    "RCG[to]": "0.5",
    "AFYChYYIncomeRevenues[id]": "AFYChYYIncomeRevenues",
    "AFYChYYIncomeRevenues[from]": "0.2",
    "AFYChYYIncomeRevenues[to]": "82.3158"
}

def baza():
    conn = sqlite3.connect("spolki.db") # tworzy plik bazy danych, rozpoczecie pracy z bazą 
    kursor = conn.cursor() # narzedzie do wykonywania komend sql
    kursor.execute("""  
        CREATE TABLE IF NOT EXISTS spolki (  
            ticker TEXT PRIMARY KEY,
            nazwa TEXT,
            rynek TEXT,
            cena REAL,
            nazwa_espi TEXT,
            zatwierdzona INTEGER DEFAULT 0 -- 0 = nierozpatrzona, 1 = zatwierdzona, 2 = odrzucona
        )
    """)   # Tworzy tabele o nazwie "spolki", definiuje typy zmiennych oraz nazwy kolumn. kursor.execute wysyla komende sql do bazy 
    conn.commit()  # zatwierdzenie zmian
    return conn
def waliduj_input(ticker, nazwa, rynek, nazwa_espi):
    if not re.match(r'^[A-Z0-9]{1,10}$', ticker):
        return False, "Ticker moze zawierac tylko litery i cyfry, max 10 znakow"
    if rynek not in ["GPW", "NC"]:
        return False, "Rynek musi byc GPW lub NC"
    if not re.match(r'^[A-Za-z0-9 \(\)\.\-\_]{1,100}$', nazwa):
        return False, "Nazwa zawiera niedozwolone znaki"
    if not re.match(r'^[A-Za-z0-9 ]{1,100}$', nazwa_espi):
        return False, "Nazwa ESPI zawiera niedozwolone znaki"
    
    return True, None

def pobierz_spolki(conn):
    try:
        response = requests.post(URL, headers=headers1, data=PAYLOAD, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Blad polaczenia: {e}")
        return

    dane = response.json()
    spolki = dane["data"]
    print(f"Znaleziono {len(spolki)} spolek:\n")

    kursor = conn.cursor()
    for s in spolki:
        sym = s["Symbol"]
        kursor.execute("""
            INSERT OR IGNORE INTO spolki (ticker, nazwa, rynek, cena)
            VALUES (?, ?, ?, ?)
        """, (sym["shortName"], sym["displayName"], s["Market"], sym["close"]))
        print(f"  {sym['displayName']:<30} {s['Market']:<4} cena: {sym['close']} PLN")

    conn.commit()
    print(f"\nZapisano do bazy danych spolki.db")
                       
def dodaj_spolke(ticker, nazwa, rynek, nazwa_espi, conn):
    poprawny, blad = waliduj_input(ticker, nazwa, rynek, nazwa_espi)
    if not poprawny:
        print(f"Blad walidacji: {blad}")
        return

    kursor = conn.cursor()
    try:
        kursor.execute("""
            INSERT INTO spolki (ticker, nazwa, rynek, nazwa_espi, zatwierdzona)
            VALUES (?, ?, ?, ?, 1)
        """, (ticker, nazwa, rynek, nazwa_espi))
        conn.commit()
        print(f"Dodano: {ticker} ({nazwa})")
    except sqlite3.IntegrityError:
        print(f"Spolka {ticker} juz istnieje w bazie")

if __name__ == "__main__":
    conn = baza()
    print("Wybierz tryb:")
    print("1 - Skan BiznesRadar")
    print("2 - Dodaj spolke recznie")
    tryb = input("Tryb: ").strip()

    if tryb == "1":
        pobierz_spolki(conn)
    elif tryb == "2":
        ticker = input("Ticker (np. CRE): ").strip().upper()
        nazwa = input("Nazwa (np. CRE (CREOTECH)): ").strip()
        rynek = input("Rynek (GPW / NC): ").strip().upper()
        nazwa_espi = input("Nazwa do wyszukiwania ESPI (np. Creotech): ").strip()
        dodaj_spolke(ticker, nazwa, rynek, nazwa_espi, conn)
    else:
        print("Nieznany tryb")
    conn.close()

