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
def send_message_to_telegram(text, meal_type):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHANNEL_ID, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, data=payload)
        if response.ok:
            message_id = response.json().get("result", {}).get("message_id")
            if message_id:
                # Save message ID with meal type
                with open("message_ids.txt", "a") as file:
                    file.write(f"{message_id},{meal_type}\n")
                    
                # Delete previous message for this meal type if it exists
                delete_previous_meal_message(meal_type, message_id)
                    
                logging.info(f"Mensagem de {meal_type} enviada com sucesso. ID: {message_id}")
            return message_id
        else:
            logging.error(f"Erro ao enviar mensagem. Resposta: {response.text}")
    except Exception as e:
        logging.exception("Erro inesperado ao enviar mensagem para o Telegram")
    return None

def delete_previous_meal_message(meal_type, current_message_id):
    try:
        messages = []
        # Read all messages
        with open("message_ids.txt", "r") as file:
            messages = [line.strip().split(",") for line in file if line.strip()]
        
        # Find previous message of the same meal type
        for msg_id, msg_type in messages[:-1]:  # Exclude the last message (current one)
            if msg_type == meal_type:
                delete_message_from_telegram(int(msg_id))
                logging.info(f"Mensagem anterior de {meal_type} (ID: {msg_id}) deletada.")
        
        # Clean up the message_ids.txt file to keep only the latest message for each type
        latest_messages = {}
        for msg_id, msg_type in messages:
            latest_messages[msg_type] = msg_id
            
        with open("message_ids.txt", "w") as file:
            for msg_type, msg_id in latest_messages.items():
                file.write(f"{msg_id},{msg_type}\n")
                
    except FileNotFoundError:
        logging.warning("Arquivo message_ids.txt não encontrado.")
    except Exception as e:
        logging.exception("Erro ao deletar mensagem anterior")

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
            message_lines = file.readlines()
        for line in message_lines:
            line = line.strip()
            if line:
                message_id = line.split(",")[0]  # Get just the message ID part
                delete_message_from_telegram(int(message_id))
        # Clear the file after deleting all messages
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
    if not menu or not isinstance(menu, str):
        return ""
    
    formated_menu = [line.strip() for line in menu.split("\n") if line.strip()]
    output_menu = ""
    
    # Define menu sections with their emojis
    menu_sections = {
        "Salada": "🥗",
        "Prato Principal": "🍛",
        "Guarnição": "🍚",
        "Sobremesa": "🍨"
    }
    
    forbidden_words = ["sujeito", "Informamos", "Opção", "cardápio", "CARDÁPIO"]
    current_section = None
    
    # Define fixed accompaniments
    fixed_accompaniments = {"Arroz Branco", "Arroz Integral", "Feijão"}
    
    # Start with the fixed Acompanhamento section
    output_menu += "🍟 <b>Acompanhamento</b>: \n"
    for staple in fixed_accompaniments:
        output_menu += f"    - {staple}\n"
    
    for item in formated_menu:
        # Skip lines with forbidden words, Acompanhamento section, and fixed accompaniments
        if (any(word.lower() in item.lower() for word in forbidden_words) or 
            "Acompanhamento" in item or 
            any(acc.lower() in item.lower() for acc in fixed_accompaniments)):
            continue
            
        # Rest of the function remains the same...
        item = item.split("(")[0].strip()
        
        if item in menu_sections:
            current_section = item
            output_menu += f"\n{menu_sections[item]} <b>{item}</b>: \n"
            continue
            
        if current_section and item:
            items = [sub_item.strip() for sub_item in item.split(",")]
            
            seen_items = set()
            for sub_item in items:
                if sub_item and len(sub_item) > 1 and sub_item.lower() not in seen_items:
                    output_menu += f"    - {sub_item}\n"
                    seen_items.add(sub_item.lower())
    
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
    
    if not menu:
        logging.error("Erro ao acessar o cardápio.")
        return
        
    try:
        # Get current time to determine meal type
        current_time = datetime.datetime.now().time()
        meal_type = "Jantar" if current_time.hour >= 14 else "Almoço"
        
        # Only process the relevant meal
        menu_text = menu.get(meal_type, "")
        if not menu_text:
            logging.info(f"Cardápio para {meal_type} não encontrado.")
            return
            
        current_hash = hashlib.md5(menu_text.encode("utf-8")).hexdigest()
        
        # Store hashes separately for lunch and dinner
        hash_file = f"menu_hash_{meal_type.lower()}.txt"
        
        try:
            with open(hash_file, "r") as file:
                previous_hash = file.read().strip()
        except FileNotFoundError:
            previous_hash = None
            
        if current_hash != previous_hash:
            # Update hash file
            with open(hash_file, "w") as file:
                file.write(current_hash)
                
            # Format and send message
            message = format_message({meal_type: menu_text})
            if message:
                logging.info(f"Cardápio de {meal_type} atualizado. Enviando para o Telegram...")
                send_message_to_telegram(message, meal_type)
        else:
            logging.info(f"Nenhuma alteração no cardápio de {meal_type} detectada.")
            
    except Exception as e:
        logging.exception("Erro ao processar atualização do cardápio")

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
