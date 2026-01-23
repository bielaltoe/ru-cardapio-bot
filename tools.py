import requests
from bs4 import BeautifulSoup
import datetime
import logging
import os
import json
try:
    from google import genai
except Exception:
    genai = None

from config import Config
from pydantic import BaseModel, Field
from typing import List

# --- DEFINIÇÃO DOS SCHEMAS (MODELOS) ---
class MenuSections(BaseModel):
    salada: List[str] = Field(default_factory=list, description="Lista de opções de salada.")
    prato_principal: List[str] = Field(default_factory=list, description="Lista de pratos principais (carne, peixe, ovos, etc).")
    acompanhamento: List[str] = Field(default_factory=list, description="Acompanhamentos variáveis (farofa, macarrão, etc). Não incluir arroz e feijão aqui.")
    guarnicao: List[str] = Field(default_factory=list, description="Guarnições (legumes, purês, etc).")
    sobremesa: List[str] = Field(default_factory=list, description="Opções de sobremesa (doces ou frutas).")
    suco: List[str] = Field(default_factory=list, description="Sabores de suco disponíveis.")

class MenuResponse(BaseModel):
    meal: str = Field(description="Tipo da refeição identificada: 'Almoço' ou 'Jantar'")
    sections: MenuSections

class Tools:
    def __init__(self):
        config = Config()
        self.TELEGRAM_TOKEN = config.TELEGRAM_TOKEN
        self.CHANNEL_ID = config.CHANNEL_ID
        self.GOOGLE_API_KEY = config.GOOGLE_API_KEY

    # --- CONTROLE DE ENVIO DIÁRIO ---

    def get_control_file_path(self):
        return "daily_control.json"

    def check_if_sent_today(self, meal_type):
        """Verifica se a refeição já foi enviada na data de hoje."""
        today = datetime.date.today().isoformat()
        file_path = self.get_control_file_path()
        
        if not os.path.exists(file_path):
            return False
            
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
                return data.get(meal_type) == today
        except Exception:
            return False

    def mark_as_sent(self, meal_type):
        """Salva no arquivo que a refeição foi enviada hoje."""
        today = datetime.date.today().isoformat()
        file_path = self.get_control_file_path()
        data = {}
        
        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
            except Exception:
                data = {}
                
        data[meal_type] = today
        
        with open(file_path, "w") as f:
            json.dump(data, f)

    # --- MENSAGENS E TELEGRAM ---

    def send_message_to_telegram(self, text, meal_type):
        url = f"https://api.telegram.org/bot{self.TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": self.CHANNEL_ID, "text": text, "parse_mode": "HTML"}
        try:
            response = requests.post(url, data=payload)
            if response.ok:
                message_id = response.json().get("result", {}).get("message_id")
                if message_id:
                    # Salva ID da mensagem em JSON Lines
                    with open("message_ids.json", "a") as file:
                        entry = {"message_id": message_id, "meal_type": meal_type}
                        json.dump(entry, file)
                        file.write("\n")
                        
                    # Apaga mensagem anterior do mesmo tipo
                    self.delete_previous_meal_message(meal_type, message_id)
                        
                    logging.info(f"Mensagem de {meal_type} enviada com sucesso. ID: {message_id}")
                return message_id
            else:
                logging.error(f"Erro ao enviar mensagem. Resposta: {response.text}")
        except Exception as e:
            logging.exception("Erro inesperado ao enviar mensagem para o Telegram")
        return None

    def delete_previous_meal_message(self, meal_type, current_message_id):
        try:
            messages = []
            if not os.path.exists("message_ids.json"):
                return

            with open("message_ids.json", "r") as file:
                for line in file:
                    if line.strip():
                        try:
                            messages.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            
            # Encontra a mensagem anterior mais recente do mesmo tipo
            for msg in reversed(messages[:-1]): # Ignora a última (atual)
                if msg.get("meal_type") == meal_type:
                    msg_id = msg.get("message_id")
                    try:
                        ok = self.delete_message_from_telegram(msg_id)
                        if ok:
                            logging.info(f"Mensagem anterior de {meal_type} (ID: {msg_id}) deletada.")
                        else:
                            logging.warning(f"Falha ao deletar msg anterior (ID: {msg_id}).")
                    except Exception:
                        logging.exception(f"Erro ao deletar msg anterior (ID: {msg_id})")
                    break 
            
            # Limpeza do arquivo (mantém apenas a última de cada tipo)
            latest_map = {}
            for msg in messages:
                latest_map[msg["meal_type"]] = msg["message_id"]
                
            with open("message_ids.json", "w") as file:
                for m_type, m_id in latest_map.items():
                    json.dump({"message_id": m_id, "meal_type": m_type}, file)
                    file.write("\n")
                    
        except Exception as e:
            logging.exception("Erro ao gerenciar histórico de mensagens")

    def delete_message_from_telegram(self, message_id):
        url = f"https://api.telegram.org/bot{self.TELEGRAM_TOKEN}/deleteMessage"
        payload = {"chat_id": self.CHANNEL_ID, "message_id": message_id}
        try:
            response = requests.post(url, data=payload)
            return response.ok
        except Exception as e:
            logging.exception(f"Erro ao apagar mensagem com ID {message_id}")
            return False

    def delete_all_messages(self):
        logging.info("Iniciando exclusão de todas as mensagens...")
        try:
            if not os.path.exists("message_ids.json"):
                return
            
            with open("message_ids.json", "r") as file:
                lines = file.readlines()

            for line in lines:
                if line.strip():
                    try:
                        data = json.loads(line)
                        self.delete_message_from_telegram(data["message_id"])
                    except:
                        continue
            
            open("message_ids.json", "w").close() # Limpa arquivo
            logging.info("Todas as mensagens foram apagadas.")
        except Exception as e:
            logging.exception("Erro ao apagar todas as mensagens.")

    # --- GEMINI E PARSING ---

    def get_gemini_client(self):
        if not genai or not self.GOOGLE_API_KEY:
            return None
        try:
            return genai.Client()
        except Exception:
            return None

    def parse_menu_with_gemini(self, meal_title: str, field_html: str) -> dict | None:
        client = self.get_gemini_client()
        if not client:
            return None

        instr = (
            "Analise o HTML do cardápio universitário abaixo e extraia os itens para cada categoria. "
            "Ignore avisos de contaminação ou textos genéricos. "
            "Separe itens que estão na mesma linha."
        )
        contents = f"{instr}\n\nTítulo: {meal_title}\nHTML:\n{field_html}"

        try:
            resp = client.models.generate_content(
                model="gemini-flash-lite-latest",
                contents=contents,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": MenuResponse, 
                },
            )
            
            parsed_data: MenuResponse = resp.parsed 
            if not parsed_data:
                # Fallback caso a versão do SDK não popule .parsed automaticamente
                parsed_data = MenuResponse.model_validate_json(resp.text)

            key_map = {
                "salada": "Salada",
                "prato_principal": "Prato Principal",
                "acompanhamento": "Acompanhamento",
                "guarnicao": "Guarnição",
                "sobremesa": "Sobremesa",
                "suco": "Suco"
            }

            final_sections = {}
            for attr, display_name in key_map.items():
                items = getattr(parsed_data.sections, attr)
                if items:
                    final_sections[display_name] = items

            return {
                "meal": parsed_data.meal,
                "sections": final_sections
            }

        except Exception as e:
            logging.error(f"Erro no parsing estruturado do Gemini: {e}")
            return None

    def get_menu_content(self):
        today_date = datetime.date.today()
        url = f"https://ru.ufes.br/cardapio/{today_date}"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, "html.parser")
                menu = {}
                titles = soup.find_all("div", class_="views-field-title")
                bodies = soup.find_all("div", class_="views-field-body")
                
                for title, body in zip(titles, bodies):
                    meal_title = title.find("span", class_="field-content").get_text(strip=True)
                    body_div = body.find("div", class_="field-content")
                    field_html = str(body_div) if body_div else ""
                    meal_text = body_div.get_text("\n", strip=True) if body_div else ""

                    parsed = self.parse_menu_with_gemini(meal_title, field_html)
                    
                    # Define qual cardápio é
                    key = "Almoço" if "Almoço" in meal_title else "Jantar" if "Jantar" in meal_title else None
                    
                    if key:
                        menu[key] = parsed if parsed else meal_text
                        
                return menu
        except Exception:
            logging.exception("Erro ao obter cardápio")
        return None

    # --- FORMATAÇÃO ---
    def format_menu(self, menu):
        if not menu or not isinstance(menu, str):
            return ""
        
        formated_menu = [line.strip() for line in menu.split("\n") if line.strip()]
        output_menu = ""
        
        menu_sections = {"Salada": "🥗", "Prato Principal": "🍛", "Guarnição": "🍚", "Sobremesa": "🍨", "Suco": "🧃"}
        forbidden = ["sujeito", "Informamos", "Opção", "cardápio", "CARDÁPIO"]
        fixed_acc = {"Arroz Branco", "Arroz Integral", "Feijão"}
        
        output_menu += "🍟 <b>Acompanhamento</b>: \n"
        for staple in fixed_acc:
            output_menu += f"    - {staple}\n"
        
        current_section = None
        for item in formated_menu:
            if (any(w.lower() in item.lower() for w in forbidden) or 
                "Acompanhamento" in item or 
                any(acc.lower() in item.lower() for acc in fixed_acc)):
                continue
                
            item = item.split("(")[0].strip()
            
            if item in menu_sections:
                current_section = item
                output_menu += f"\n{menu_sections[item]} <b>{item}</b>: \n"
                continue
                
            if current_section and item:
                items = [sub.strip() for sub in item.split(",")]
                seen = set()
                for sub in items:
                    if sub and len(sub) > 1 and sub.lower() not in seen:
                        output_menu += f"    - {sub}\n"
                        seen.add(sub.lower())
        return output_menu

    def format_menu_structured(self, menu_sections: dict) -> str:
        if not isinstance(menu_sections, dict):
            return ""

        emojis = {"Salada": "🥗", "Prato Principal": "🍛", "Acompanhamento": "🍟", 
                  "Guarnição": "🍚", "Sobremesa": "🍨", "Suco": "🧃"}
        order = ["Acompanhamento", "Salada", "Prato Principal", "Guarnição", "Sobremesa", "Suco"]
        
        fixed = ["Arroz Branco", "Arroz Integral", "Feijão"]
        if not menu_sections.get("Acompanhamento"):
            menu_sections["Acompanhamento"] = fixed

        out = []
        for key in order:
            items = menu_sections.get(key)
            if not items: continue
            
            if isinstance(items, str):
                items = [s.strip() for s in items.split("/") if s.strip()]
            else:
                items = list(dict.fromkeys([s.strip() for s in items if s.strip()])) # Remove duplicates

            out.append(f"{emojis.get(key, '•')} <b>{key}</b>: ")
            for it in items:
                out.append(f"    - {it}")
            out.append("")
        return "\n".join(out).rstrip()


    def format_message(self, menu):
        if not menu: return None
        today = datetime.date.today().strftime("%d/%m/%Y")
        
        if "Jantar" in menu:
            header = f"<b>📅 Jantar do dia {today}</b>\n\n"
            val = menu["Jantar"]
        else:
            header = f"<b>📅 Almoço do dia {today}</b>\n\n"
            val = menu["Almoço"]

        if isinstance(val, dict) and val.get("sections"):
            body = self.format_menu_structured(val["sections"])
        else:
            body = self.format_menu(val)

        return header + body