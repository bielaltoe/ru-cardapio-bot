import requests
from bs4 import BeautifulSoup
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

from config import Config
from tools import Tools

def check_update(tools: Tools) -> None:
    logging.info("Verificando atualizações do cardápio...")
    
    # Define qual refeição estamos procurando baseada na hora
    current_hour = datetime.datetime.now().hour
    # Lógica: Até 13h busca almoço, depois das 14h busca jantar (ajuste conforme necessidade do RU)
    target_meal_type = "Jantar" if current_hour >= 14 else "Almoço"

    # 1. VERIFICAÇÃO DE SEGURANÇA: Já enviamos hoje?
    if tools.check_if_sent_today(target_meal_type):
        logging.info(f"O {target_meal_type} de hoje já foi enviado. Pulando verificação.")
        return

    # Se não enviou, busca o conteúdo
    menu = tools.get_menu_content()
    
    if not menu:
        logging.error("Erro ao acessar o cardápio ou site fora do ar.")
        return
        
    try:
        menu_obj = menu.get(target_meal_type)

        if not menu_obj:
            logging.info(f"Cardápio para {target_meal_type} ainda não disponível no site.")
            return

        # Formata a mensagem
        message = tools.format_message({target_meal_type: menu_obj})

        if message:
            logging.info(f"Enviando cardápio de {target_meal_type}...")
            # Envia a mensagem
            msg_id = tools.send_message_to_telegram(message, target_meal_type)
            
            # Se enviou com sucesso, marca como enviado hoje para não repetir
            if msg_id:
                tools.mark_as_sent(target_meal_type)
        else:
            logging.info(f"Mensagem vazia gerada para {target_meal_type}.")
            
    except Exception as e:
        logging.exception("Erro ao processar atualização do cardápio")


if __name__ == "__main__":
    tools = Tools()
    config = Config()

    # Dispara uma mensagem de teste no canal atual e sai (útil para DEV)
    if os.getenv("TEST_DEV_SEND") == "1":
        try:
            test_text = f"Mensagem de teste do RU-bot ({config.APP_ENV or 'prod'}) - {datetime.datetime.now().isoformat(timespec='seconds')}"
            tools.send_message_to_telegram(test_text, "Almoço")
        except Exception:
            logging.exception("Falha ao enviar mensagem de teste")
        sys.exit(0)

    logging.info("Monitoramento iniciado...")

    # Agendar a execução a cada 6 minutos para verificar se o cardápio saiu
    schedule.every(6).minutes.do(check_update)

    # Executa imediatamente ao iniciar (para não esperar 6 min na primeira vez)
    check_update(tools)

    # Agendar a exclusão das mensagens à meia-noite
    schedule.every().day.at("23:59").do(tools.delete_all_messages)

    while True:
        schedule.run_pending()
        time.sleep(1)
