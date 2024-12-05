import requests
from bs4 import BeautifulSoup
import hashlib
import schedule
import time
import datetime
import logging
import os
from dotenv import load_dotenv

load_dotenv()
# Informações do Telegram

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
# Configuração do logging
logging.basicConfig(
    level=logging.DEBUG,  # Defina o nível de detalhe desejado
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("app.log"),  # Salva logs em um arquivo
        logging.StreamHandler()         # Mostra logs no console
    ]
)


# Função para enviar mensagem para o Telegram
def send_message_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHANNEL_ID, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, data=payload)
        if response.ok:
            message_id = response.json().get("result", {}).get("message_id")
            if message_id:
                with open("message_ids.txt", "a") as file:
                    file.write(f"{message_id}\n")
                logging.info(f"Mensagem enviada com sucesso. ID: {message_id}")
            return message_id
        else:
            logging.error(f"Erro ao enviar mensagem. Resposta: {response.text}")
    except Exception as e:
        logging.exception("Erro inesperado ao enviar mensagem para o Telegram")
    return None

# Função para apagar mensagens do Telegram
def delete_message_from_telegram(message_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage"
    payload = {"chat_id": CHANNEL_ID, "message_id": message_id}
    try:
        response = requests.post(url, data=payload)
        if response.ok:
            logging.info(f"Mensagem com ID {message_id} apagada com sucesso.")
        else:
            logging.warning(f"Falha ao apagar mensagem com ID {message_id}. Resposta: {response.text}")
        return response.ok
    except Exception as e:
        logging.exception(f"Erro ao apagar mensagem com ID {message_id}")


# Função para apagar todas as mensagens à meia-noite
def delete_all_messages():
    logging.info("Iniciando exclusão de todas as mensagens...")
    try:
        with open("message_ids.txt", "r") as file:
            message_ids = file.readlines()
        for message_id in message_ids:
            message_id = message_id.strip()
            if message_id:
                delete_message_from_telegram(int(message_id))
        with open("message_ids.txt", "w") as file:
            file.write("")
        logging.info("Todas as mensagens foram apagadas com sucesso.")
    except FileNotFoundError:
        logging.warning("Nenhum arquivo de IDs de mensagens encontrado para exclusão.")
    except Exception as e:
        logging.exception("Erro ao apagar todas as mensagens.")


# Função para obter o conteúdo do cardápio
def get_menu_content():
    today_date = datetime.date.today()
    url = f"https://ru.ufes.br/cardapio/{today_date}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            logging.info(f"Acessando cardápio: {url}")
            soup = BeautifulSoup(response.content, "html.parser")
            menu = {}
            titles = soup.find_all("div", class_="views-field-title")
            bodies = soup.find_all("div", class_="views-field-body")
            for title, body in zip(titles, bodies):
                meal_title = title.find("span", class_="field-content").get_text(strip=True)
                meal_content = body.find("div", class_="field-content").get_text(separator="\n", strip=True)
                if "Almoço" in meal_title:
                    menu["Almoço"] = meal_content
                elif "Jantar" in meal_title:
                    menu["Jantar"] = meal_content
            return menu
        else:
            logging.error(f"Erro ao acessar cardápio: {response.status_code}")
    except Exception as e:
        logging.exception("Erro ao obter o cardápio")
    return None


def format_menu(menu):
    
    formated_menu = menu.split("\n")
    # print(formated_menu)
    output_menu = ""
    forbidden_words = ["sujeito", "Informamos", "Opção"]
    for item in formated_menu:

        skip_next = False

        for fb in forbidden_words:
            if fb in item:
                skip_next = True
                break
        if skip_next:
            continue

        item = item.split("(")[0]

        if item == "Salada":
            output_menu += f"\n🥗 <b>{item}</b>: \n"
            continue
        elif item == "Prato Principal":
            output_menu += f"\n🍛 <b>{item}</b>: \n"
            continue
        elif item == "Guarnição":
            output_menu += f"\n🍚 <b>{item}</b>: \n"
            continue
        elif item == "Acompanhamento":
            output_menu += f"\n🍟 <b>{item}</b>: \n"
            continue
        elif item == "Sobremesa":
            output_menu += f"\n🍨 <b>{item}</b>: \n"
            continue
        else:
            for item in item.split(", "):
                for item in item.split(" e "):
                    output_menu += f"    - {item}\n"
            
    return output_menu


# Função para formatar a mensagem para o Telegram com a data incluída
def format_message(menu):
    if not menu:
        return None

    today_date = datetime.date.today().strftime("%d/%m/%Y")
    message = ""

    if "Jantar" in menu:
        message += f"<b>📅 Jantar do dia {today_date}</b>\n\n"

        output_menu = format_menu(menu["Jantar"])
    else:
        message += f"<b>📅 Almoço do dia {today_date}</b>\n\n"
        output_menu = format_menu(menu["Almoço"])
    message += output_menu

    return message

# Função para verificar atualizações e enviar o cardápio para o Telegram
def check_update():
    logging.info("Verificando atualizações do cardápio...")
    menu = get_menu_content()
    if menu:
        menu_text = "\n\n".join(menu.values())
        current_hash = hashlib.md5(menu_text.encode("utf-8")).hexdigest()
        try:
            with open("menu_hash.txt", "r") as file:
                previous_hash = file.read()
        except FileNotFoundError:
            previous_hash = None
        if current_hash != previous_hash:
            with open("menu_hash.txt", "w") as file:
                file.write(current_hash)
            message = format_message(menu)
            if message:
                logging.info("Cardápio atualizado. Enviando para o Telegram...")
                send_message_to_telegram(message)
        else:
            logging.info("Nenhuma alteração no cardápio detectada.")
    else:
        logging.error("Erro ao acessar o cardápio.")

logging.info("Monitoramento iniciado...")
# Agendar a execução a cada 6 minutos para o envio do cardápio
schedule.every(6).minutes.do(check_update)
# Executa imediatamente ao iniciar
logging.info("Executando verificação inicial do cardápio...")
check_update()  # Chamada inicial
# Agendar a exclusão das mensagens à meia-noite
schedule.every().day.at("23:59").do(delete_all_messages)

while True:
    schedule.run_pending()
    time.sleep(1)
