import requests 
import sqlite3
import anthropic 
import os
import time 
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
Base_URL = "https://espiebi.pap.pl"
headers1 = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

PRZEPUSZCZAJ = [
    "umow", "kontrakt", "transakcj", "dofinansowan", "wezwan",
    "szacunkow", "strategiczn", "listu intencyjn", "term sheet",
    "test", "art. 19"
]

ODRZUCAJ = [
    "harmonogram", "walne", "statut", "powołan",
    "odwołan", "liczb", "rezygnacj"
]

klient = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def baza():
    conn = sqlite3.connect("spolki.db")
    kursor = conn.cursor()
    kursor.execute("""
        CREATE TABLE IF NOT EXISTS raporty (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            ticker TEXT,
            typ TEXT,
            data TEXT,
            numer TEXT,
            tytul TEXT,
            link TEXT UNIQUE,  
            tresc TEXT,
            podsumowanie TEXT
        ) 
    """)
    
    conn.commit()
    return conn

def filtruj(tytul):
    tytul_lower = tytul.lower()
    for slowo in ODRZUCAJ:
        if slowo in tytul_lower:
            return False
    for slowo in PRZEPUSZCZAJ:
        if slowo in tytul_lower:
            return True
    return False



def pobierz_tresc(link):
    try:
        response = requests.get(link, headers=headers1, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        sekcja = soup.find("div", class_="arkusz")
        if not sekcja:
            return None
        return sekcja.get_text(separator=" ", strip=True)
    except requests.exceptions.RequestException as e:
        print(f" Blad pobierania tresci {e}")
        return None


def analizuj_claude(tytul, tresc):
    try:
        wiadomosc = klient.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": f""" Jestes analitykiem inwestycyjnym Przeanalizuj ten raport ESPI i wyciągnij TYLKO:
1. Co się wydarzyło (1 zdanie)
2. Kluczowe liczby/kwoty jeśli są
3. Ocena ważności: WYSOKA / ŚREDNIA / NISKA

Tytuł: {tytul}
Treść: {tresc[:2000]}

Odpowiedz krótko, maksymalnie 4 zdania, bez formatowania Markdown, bez gwiazdek i hashtagów."""
            }]
        )
        return wiadomosc.content[0].text 
    except anthropic.APIError as e:
        print(f" Blad API Claude {e}")
        return None
    
def wysylaj_telegram(ticker, tytul, podsumowanie, data):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        return

    if "WYSOKA" in podsumowanie.upper():
        emoji = "🔴"
    elif "SREDNIA" in podsumowanie.upper() or "ŚREDNIA" in podsumowanie.upper():
        emoji = "🟡"
    else:
        emoji = "🟢"

    tekst = f"{emoji} NOWY RAPORT - {ticker} ({data})\n\n{tytul}\n\n{podsumowanie}"

    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": tekst},
            timeout=10
        )
        print(f"  Wyslano powiadomienie Telegram dla {ticker}")
    except requests.exceptions.RequestException as e:
        print(f"  Blad Telegram: {e}")

def pobierz_raporty(ticker, nazwa_url, conn):
    
    try:
        data_od = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        url = f"{Base_URL}/wyszukiwarka?created={data_od}&search={nazwa_url}"
        print(f"Szukam: {url}")
        response = requests.get(url, headers=headers1, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Blad polaczenia dla {ticker}: {e}")
        return

    soup = BeautifulSoup(response.text, "html.parser")
    print(f"Znaleziono dni: {len(soup.find_all('div', class_='day'))}")
    
    zapisane = 0
    odrzucone = 0
    kursor = conn.cursor()

    for dzien in soup.find_all("div", class_="day"):
        data = dzien.find("h2", class_="date")
        data = data.text.strip() if data else "brak daty"

        for news in dzien.find_all("li", class_="news"):
            typ = news.find("div", class_="badge")
            numer = news.find_all("div", class_="hour")
            link_tag = news.find("a", class_="link")
            if not link_tag:
                continue

            tytul = link_tag.text.strip()
            if nazwa_url.lower() not in tytul.lower():
                continue

            link = Base_URL + link_tag["href"]
            typ = typ.text.strip() if typ else ""
            numer = numer[1].text.strip() if len(numer) > 1 else ""

            if filtruj(tytul):
                kursor.execute("SELECT id FROM raporty WHERE link = ?", (link,))
                if kursor.fetchone():
                    continue

                print(f" Pobieram: {tytul[:60]}...")
                time.sleep(1)
                tresc = pobierz_tresc(link)
                podsumowanie = analizuj_claude(tytul,tresc) if tresc else None
                if podsumowanie:
                    print(f" -> {podsumowanie[:100]}...")
                
                kursor.execute(""" 
                    INSERT OR IGNORE INTO raporty (ticker, typ, data, numer, tytul, link, tresc, podsumowanie)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (ticker, typ, data, numer, tytul, link, tresc, podsumowanie))
                if kursor.rowcount > 0:
                    zapisane += 1
                    if podsumowanie:
                        wysylaj_telegram(ticker, tytul, podsumowanie, data)
            else:
                odrzucone += 1

    conn.commit()
    print(f"{ticker}: zapisano {zapisane}, odrzucono {odrzucone}")

def pobierz_zatwierdzone_tickery(conn):
    kursor = conn.cursor()
    kursor.execute("SELECT ticker, nazwa_espi FROM spolki WHERE zatwierdzona = 1")
    return [(ticker, nazwa) for ticker, nazwa in kursor.fetchall()]
if __name__ == "__main__":
    conn = baza()
    tickery = pobierz_zatwierdzone_tickery(conn)
    print(f"Znaleziono {len(tickery)} zatwierdzonych spolek\n")
    for ticker, nazwa_url in tickery:
        pobierz_raporty(ticker, nazwa_url, conn)
    conn.close()
    
