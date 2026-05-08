import datetime
import logging
import os
import sys
import time

import schedule

from config import Config
from tools import Tools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def check_update(tools: Tools) -> None:
    logging.info("Verificando atualizações do cardápio...")

    target_meal_type = "Jantar" if datetime.datetime.now().hour >= 14 else "Almoço"

    if tools.check_if_sent_today(target_meal_type):
        logging.info("%s de hoje já foi enviado. Pulando.", target_meal_type)
        return

    menu = tools.get_menu_content()
    if not menu:
        logging.error("Erro ao acessar o cardápio ou site fora do ar.")
        return

    meal_data = menu.get(target_meal_type)
    if not meal_data:
        logging.info("Cardápio para %s ainda não disponível.", target_meal_type)
        return

    if tools.send_message(meal_data, target_meal_type):
        tools.mark_as_sent(target_meal_type)
    else:
        logging.warning("Nenhum canal recebeu a mensagem de %s.", target_meal_type)


if __name__ == "__main__":
    tools = Tools()
    config = Config()

    if os.getenv("TEST_DEV_SEND") == "1":
        try:
            now = datetime.datetime.now().isoformat(timespec="seconds")
            test_menu = {
                "meal": "Almoço",
                "sections": {
                    "Salada": ["Alface", "Tomate & Cebola"],
                    "Prato Principal": ["Strogonoff <de> frango"],
                    "Sobremesa": ["Gelatina"],
                },
            }
            tools.send_message(test_menu, "Almoço")
            logging.info("Teste enviado às %s (env=%s)", now, config.APP_ENV or "prod")
        except Exception:
            logging.exception("Falha ao enviar mensagem de teste")
        sys.exit(0)

    logging.info("Monitoramento iniciado...")

    schedule.every(6).minutes.do(check_update, tools)
    schedule.every().day.at("23:59").do(tools.delete_all_messages)

    check_update(tools)

    while True:
        schedule.run_pending()
        time.sleep(1)
