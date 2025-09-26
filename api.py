import requests
from bs4 import BeautifulSoup
import hashlib
import schedule
import time
import datetime
import logging
import os
from dotenv import load_dotenv
import json
import sys
try:
    from google import genai
except Exception:
    genai = None

load_dotenv()
# Informações do Telegram

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Alterna para DEV caso APP_ENV=dev
APP_ENV = os.getenv("APP_ENV")
if APP_ENV == "dev":
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_DEV_TOKEN", TELEGRAM_TOKEN)
    CHANNEL_ID = os.getenv("CHANNEL_DEV_ID", CHANNEL_ID)

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
        
        # Encontra a mensagem anterior mais recente do mesmo tipo (antes da atual)
        for msg_id, msg_type in reversed(messages[:-1]):  # Exclui a última (atual) e percorre do fim para o início
            if msg_type == meal_type:
                try:
                    ok = delete_message_from_telegram(int(msg_id))
                    if ok:
                        logging.info(f"Mensagem anterior de {meal_type} (ID: {msg_id}) deletada.")
                    else:
                        logging.warning(f"Falha ao deletar mensagem anterior de {meal_type} (ID: {msg_id}).")
                except Exception:
                    logging.exception(f"Erro ao deletar mensagem anterior de {meal_type} (ID: {msg_id})")
                break  # Deleta apenas a última anterior
        
        # Limpa o arquivo para manter apenas a última mensagem de cada tipo
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


def get_gemini_client():
    """Inicializa e retorna o cliente Gemini, se disponível e configurado."""
    if not genai:
        logging.warning("Pacote google-genai não instalado. Usando fallback sem Gemini.")
        return None
    if not GOOGLE_API_KEY:
        logging.warning("GOOGLE_API_KEY não definido. Usando fallback sem Gemini.")
        return None
    try:
        # O client lê a chave do ambiente GOOGLE_API_KEY
        client = genai.Client()
        return client
    except Exception:
        logging.exception("Falha ao inicializar o cliente Gemini. Usando fallback sem Gemini.")
        return None


def parse_menu_with_gemini(meal_title: str, field_html: str) -> dict | None:
    """Usa Gemini para transformar o HTML do bloco do cardápio em um dicionário estruturado.
    Retorna um dict no formato:
    {
      "meal": "Almoço" | "Jantar",
      "sections": {
         "Salada": ["..."],
         "Prato Principal": ["..."],
         "Acompanhamento": ["..."],
         "Guarnição": ["..."],
         "Sobremesa": ["..."],
         "Suco": ["..."]
      }
    }
    """
    client = get_gemini_client()
    if not client:
        return None

    instr = (
        "Você receberá um trecho de HTML correspondente ao cardápio de uma refeição do restaurante universitário. "
        "Extraia e normalize as informações em JSON puro (somente JSON, sem explicações). "
        "Normalize as chaves das seções para exatamente estes nomes quando existirem: "
        "Salada, Prato Principal, Acompanhamento, Guarnição, Sobremesa, Suco. "
        "Remova observações entre parênteses e quaisquer notas como 'sujeito a alterações' e avisos de contaminação cruzada. "
        "Divida múltiplos itens separados por vírgula ou '/' em uma lista de strings individuais, sem duplicatas, mantendo capitalização natural. "
        "Responda somente com JSON no formato: {\n"
        "  \"meal\": \"Almoço|Jantar\",\n"
        "  \"sections\": {\n"
        "     \"Salada\": [""], \"Prato Principal\": [""], \"Acompanhamento\": [""], \"Guarnição\": [""], \"Sobremesa\": [""], \"Suco\": [""]\n"
        "  }\n"
        "} (omite chaves ausentes em 'sections' se não existirem)."
    )

    contents = (
        f"Título da refeição: {meal_title}\n\n"
        f"HTML:\n{field_html}"
    )

    try:
        resp = client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=f"{instr}\n\n{contents}"
        )
        text = (resp.text or "").strip()
        if not text:
            return None
        # Tenta localizar JSON mesmo se vier dentro de bloco
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end+1]
        data = json.loads(text)
        # Validação mínima
        if not isinstance(data, dict) or "sections" not in data:
            return None
        return data
    except Exception:
        logging.exception("Falha ao parsear cardápio com Gemini")
        return None


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
            menu: dict[str, dict | str] = {}
            titles = soup.find_all("div", class_="views-field-title")
            bodies = soup.find_all("div", class_="views-field-body")
            for title, body in zip(titles, bodies):
                meal_title = title.find("span", class_="field-content").get_text(strip=True)
                body_div = body.find("div", class_="field-content")
                field_html = str(body_div) if body_div else ""

                # Texto bruto (estável) para hash
                meal_content_text = body_div.get_text(separator="\n", strip=True) if body_div else ""

                # Tenta usar Gemini para parse estruturado
                parsed = parse_menu_with_gemini(meal_title, field_html)
                if parsed is not None:
                    # Anexa fonte para hashing estável
                    parsed["source"] = meal_content_text

                if "Almoço" in meal_title:
                    menu["Almoço"] = parsed if parsed else meal_content_text
                elif "Jantar" in meal_title:
                    menu["Jantar"] = parsed if parsed else meal_content_text
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


def format_menu_structured(menu_sections: dict) -> str:
    """Formata um dicionário de seções em texto com emojis."""
    if not isinstance(menu_sections, dict):
        return ""

    emojis = {
        "Salada": "🥗",
        "Prato Principal": "🍛",
        "Acompanhamento": "🍟",
        "Guarnição": "🍚",
        "Sobremesa": "🍨",
        "Suco": "🧃",
    }

    # Ordem preferida de exibição
    order = [
        "Acompanhamento",
        "Salada",
        "Prato Principal",
        "Guarnição",
        "Sobremesa",
        "Suco",
    ]

    # Se não vier acompanhamento, usa padrão fixo
    fixed_accompaniments = ["Arroz Branco", "Arroz Integral", "Feijão"]
    if "Acompanhamento" not in menu_sections or not menu_sections.get("Acompanhamento"):
        menu_sections = {**menu_sections, "Acompanhamento": fixed_accompaniments}

    out = []
    for key in order:
        items = menu_sections.get(key)
        if not items:
            continue
        # normaliza lista/str
        if isinstance(items, str):
            items = [s.strip() for s in items.split("/") if s.strip()]
        else:
            # limpa duplicatas, remove strings curtas e vazias
            seen = set()
            clean = []
            for s in items:
                s = (s or "").strip()
                if not s:
                    continue
                s_base = s.lower()
                if s_base in seen:
                    continue
                seen.add(s_base)
                clean.append(s)
            items = clean
        header = f"{emojis.get(key, '•')} <b>{key}</b>: "
        out.append(header)
        for it in items:
            out.append(f"    - {it}")
        out.append("")
    return "\n".join(out).rstrip()


# Função para formatar a mensagem para o Telegram com a data incluída
def format_message(menu):
    if not menu:
        return None

    today_date = datetime.date.today().strftime("%d/%m/%Y")
    message = ""

    if "Jantar" in menu:
        message += f"<b>📅 Jantar do dia {today_date}</b>\n\n"
        value = menu["Jantar"]
    else:
        message += f"<b>📅 Almoço do dia {today_date}</b>\n\n"
        value = menu["Almoço"]

    # Se veio estruturado (dict com 'sections'), usa formatação estruturada
    if isinstance(value, dict) and value.get("sections"):
        output_menu = format_menu_structured(value["sections"])
    else:
        # Fallback para lógica antiga baseada em string
        output_menu = format_menu(value)

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
        current_time = datetime.datetime.now().time()
        meal_type = "Jantar" if current_time.hour >= 14 else "Almoço"
        
        menu_obj = menu.get(meal_type)
        if not menu_obj:
            logging.info(f"Cardápio para {meal_type} não encontrado.")
            return
            
        # Hash estável baseado no texto bruto (source) quando disponível
        if isinstance(menu_obj, dict):
            hash_source = menu_obj.get("source") or json.dumps(menu_obj.get("sections", {}), ensure_ascii=False, sort_keys=True)
        else:
            hash_source = str(menu_obj)
        current_hash = hashlib.md5(hash_source.encode("utf-8")).hexdigest()
        
        hash_file = f"menu_hash_{meal_type.lower()}.txt"
        
        try:
            with open(hash_file, "r") as file:
                previous_hash = file.read().strip()
        except FileNotFoundError:
            previous_hash = None
            
        if current_hash != previous_hash:
            with open(hash_file, "w") as file:
                file.write(current_hash)
                
            message = format_message({meal_type: menu_obj})
            if message:
                logging.info(f"Cardápio de {meal_type} atualizado. Enviando para o Telegram...")
                send_message_to_telegram(message, meal_type)
        else:
            logging.info(f"Nenhuma alteração no cardápio de {meal_type} detectada.")
            
    except Exception as e:
        logging.exception("Erro ao processar atualização do cardápio")

# Dispara uma mensagem de teste no canal atual e sai (útil para DEV)
if os.getenv("TEST_DEV_SEND") == "1":
    try:
        test_text = f"Mensagem de teste do RU-bot ({APP_ENV or 'prod'}) - {datetime.datetime.now().isoformat(timespec='seconds')}"
        send_message_to_telegram(test_text, "Almoço")
    except Exception:
        logging.exception("Falha ao enviar mensagem de teste")
    sys.exit(0)

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
