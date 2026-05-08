import datetime
import html
import json
import logging
import os
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

try:
    from google import genai
except Exception:
    genai = None

from config import Config


# --- Schemas ---

class MenuSections(BaseModel):
    salada: List[str] = Field(default_factory=list)
    prato_principal: List[str] = Field(default_factory=list)
    acompanhamento: List[str] = Field(default_factory=list)
    guarnicao: List[str] = Field(default_factory=list)
    sobremesa: List[str] = Field(default_factory=list)
    suco: List[str] = Field(default_factory=list)


class MenuResponse(BaseModel):
    meal: str = Field(description="Almoço ou Jantar")
    sections: MenuSections


SECTION_ORDER = ["Acompanhamento", "Salada", "Prato Principal", "Guarnição", "Sobremesa", "Suco"]
SECTION_EMOJIS = {
    "Salada": "🥗",
    "Prato Principal": "🍛",
    "Acompanhamento": "🍟",
    "Guarnição": "🍚",
    "Sobremesa": "🍨",
    "Suco": "🧃",
}
FIXED_ACCOMPANIMENTS = ["Arroz Branco", "Arroz Integral", "Feijão"]
KEY_MAP = {
    "salada": "Salada",
    "prato_principal": "Prato Principal",
    "acompanhamento": "Acompanhamento",
    "guarnicao": "Guarnição",
    "sobremesa": "Sobremesa",
    "suco": "Suco",
}


class Tools:
    def __init__(self):
        cfg = Config()
        self.TELEGRAM_TOKEN = cfg.TELEGRAM_TOKEN
        self.CHANNEL_ID = cfg.CHANNEL_ID
        self.GOOGLE_API_KEY = cfg.GOOGLE_API_KEY
        self.WHATSAPP_API_URL = (cfg.WHATSAPP_API_URL or "").rstrip("/")
        self.WHATSAPP_API_KEY = cfg.WHATSAPP_API_KEY
        self.WHATSAPP_INSTANCE = cfg.WHATSAPP_INSTANCE
        self.WHATSAPP_GROUP_ID = cfg.WHATSAPP_GROUP_ID

        data_dir = os.getenv("DATA_DIR", ".")
        os.makedirs(data_dir, exist_ok=True)
        self.DAILY_CONTROL_FILE = os.path.join(data_dir, "daily_control.json")
        self.TELEGRAM_HISTORY_FILE = os.path.join(data_dir, "message_ids_telegram.json")
        self.WHATSAPP_HISTORY_FILE = os.path.join(data_dir, "message_ids_whatsapp.json")

    # --- Daily control ---

    def check_if_sent_today(self, meal_type: str) -> bool:
        today = datetime.date.today().isoformat()
        if not os.path.exists(self.DAILY_CONTROL_FILE):
            return False
        try:
            with open(self.DAILY_CONTROL_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get(meal_type) == today
        except Exception:
            return False

    def mark_as_sent(self, meal_type: str) -> None:
        today = datetime.date.today().isoformat()
        data = {}
        if os.path.exists(self.DAILY_CONTROL_FILE):
            try:
                with open(self.DAILY_CONTROL_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data[meal_type] = today
        with open(self.DAILY_CONTROL_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    # --- Message history (per channel) ---

    def _load_history(self, file_path: str) -> list:
        if not os.path.exists(file_path):
            return []
        entries = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception:
            logging.exception("Falha ao ler %s", file_path)
        return entries

    def _save_history(self, file_path: str, entries: list) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            for entry in entries:
                json.dump(entry, f, ensure_ascii=False)
                f.write("\n")

    def _append_history(self, file_path: str, entry: dict) -> None:
        with open(file_path, "a", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False)
            f.write("\n")

    def _purge_previous(self, file_path: str, meal_type: str, current_id, deleter) -> None:
        """Delete all prior messages of same meal_type. Drop them from history regardless of result."""
        entries = self._load_history(file_path)
        kept = []
        to_delete = []
        for entry in entries:
            same_meal = entry.get("meal_type") == meal_type
            is_current = str(entry.get("message_id")) == str(current_id)
            if same_meal and not is_current:
                to_delete.append(entry)
            else:
                kept.append(entry)

        for entry in to_delete:
            mid = entry.get("message_id")
            try:
                ok = deleter(mid)
                if ok:
                    logging.info("Apagada mensagem anterior de %s (ID: %s)", meal_type, mid)
                else:
                    logging.warning("Falha ao apagar mensagem anterior de %s (ID: %s)", meal_type, mid)
            except Exception:
                logging.exception("Erro apagando mensagem ID %s", mid)

        self._save_history(file_path, kept)

    # --- Telegram ---

    def _telegram_configured(self) -> bool:
        return bool(self.TELEGRAM_TOKEN and self.CHANNEL_ID)

    def send_message_to_telegram(self, text: str, meal_type: str) -> Optional[int]:
        if not self._telegram_configured():
            logging.info("Telegram não configurado; pulando envio.")
            return None

        url = f"https://api.telegram.org/bot{self.TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": self.CHANNEL_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            response = requests.post(url, data=payload, timeout=20)
        except Exception:
            logging.exception("Erro de rede ao enviar para Telegram")
            return None

        if not response.ok:
            logging.error("Telegram sendMessage falhou: %s", response.text)
            return None

        message_id = response.json().get("result", {}).get("message_id")
        if not message_id:
            logging.error("Telegram retornou sem message_id: %s", response.text)
            return None

        self._append_history(
            self.TELEGRAM_HISTORY_FILE,
            {"message_id": message_id, "meal_type": meal_type},
        )
        self._purge_previous(
            self.TELEGRAM_HISTORY_FILE,
            meal_type,
            message_id,
            self.delete_message_from_telegram,
        )
        logging.info("Telegram %s enviado. ID: %s", meal_type, message_id)
        return message_id

    def delete_message_from_telegram(self, message_id) -> bool:
        if not self._telegram_configured() or message_id is None:
            return False
        url = f"https://api.telegram.org/bot{self.TELEGRAM_TOKEN}/deleteMessage"
        payload = {"chat_id": self.CHANNEL_ID, "message_id": message_id}
        try:
            response = requests.post(url, data=payload, timeout=20)
        except Exception:
            logging.exception("Erro de rede ao apagar mensagem Telegram %s", message_id)
            return False
        if response.ok:
            return True
        logging.warning("Telegram deleteMessage %s falhou: %s", message_id, response.text)
        return False

    # --- WhatsApp (Evolution API compatible) ---

    def _whatsapp_configured(self) -> bool:
        return bool(
            self.WHATSAPP_API_URL
            and self.WHATSAPP_API_KEY
            and self.WHATSAPP_INSTANCE
            and self.WHATSAPP_GROUP_ID
        )

    def _whatsapp_headers(self) -> dict:
        return {"apikey": self.WHATSAPP_API_KEY, "Content-Type": "application/json"}

    def send_message_to_whatsapp(self, text: str, meal_type: str) -> Optional[str]:
        if not self._whatsapp_configured():
            logging.info("WhatsApp não configurado; pulando envio.")
            return None

        url = f"{self.WHATSAPP_API_URL}/message/sendText/{self.WHATSAPP_INSTANCE}"
        payload = {"number": self.WHATSAPP_GROUP_ID, "text": text}
        try:
            response = requests.post(url, json=payload, headers=self._whatsapp_headers(), timeout=30)
        except Exception:
            logging.exception("Erro de rede ao enviar para WhatsApp")
            return None

        if not response.ok:
            logging.error("WhatsApp sendText falhou (%s): %s", response.status_code, response.text)
            return None

        try:
            data = response.json()
        except ValueError:
            logging.error("Resposta WhatsApp não é JSON: %s", response.text)
            return None

        message_id = (data.get("key") or {}).get("id") or data.get("id")
        if not message_id:
            logging.warning("WhatsApp retornou sem id reconhecível: %s", data)
            return None

        self._append_history(
            self.WHATSAPP_HISTORY_FILE,
            {"message_id": message_id, "meal_type": meal_type},
        )
        self._purge_previous(
            self.WHATSAPP_HISTORY_FILE,
            meal_type,
            message_id,
            self.delete_message_from_whatsapp,
        )
        logging.info("WhatsApp %s enviado. ID: %s", meal_type, message_id)
        return message_id

    def delete_message_from_whatsapp(self, message_id) -> bool:
        if not self._whatsapp_configured() or not message_id:
            return False
        url = f"{self.WHATSAPP_API_URL}/chat/deleteMessageForEveryone/{self.WHATSAPP_INSTANCE}"
        payload = {
            "id": message_id,
            "remoteJid": self.WHATSAPP_GROUP_ID,
            "fromMe": True,
        }
        try:
            response = requests.delete(
                url, json=payload, headers=self._whatsapp_headers(), timeout=20
            )
        except Exception:
            logging.exception("Erro de rede ao apagar WhatsApp %s", message_id)
            return False
        if response.ok:
            return True
        logging.warning("WhatsApp delete %s falhou: %s", message_id, response.text)
        return False

    # --- Send to all configured channels ---

    def send_message(self, structured_menu: dict, meal_type: str) -> bool:
        any_sent = False
        if self._telegram_configured():
            text = self.format_message(structured_menu, channel="telegram")
            if text and self.send_message_to_telegram(text, meal_type):
                any_sent = True
        if self._whatsapp_configured():
            text = self.format_message(structured_menu, channel="whatsapp")
            if text and self.send_message_to_whatsapp(text, meal_type):
                any_sent = True
        return any_sent

    def delete_all_messages(self) -> None:
        logging.info("Limpando todas as mensagens registradas...")
        for file_path, deleter in (
            (self.TELEGRAM_HISTORY_FILE, self.delete_message_from_telegram),
            (self.WHATSAPP_HISTORY_FILE, self.delete_message_from_whatsapp),
        ):
            for entry in self._load_history(file_path):
                try:
                    deleter(entry.get("message_id"))
                except Exception:
                    logging.exception("Erro apagando %s", entry)
            if os.path.exists(file_path):
                open(file_path, "w").close()

    # --- Gemini parsing ---

    def get_gemini_client(self):
        if not genai or not self.GOOGLE_API_KEY:
            return None
        try:
            return genai.Client()
        except Exception:
            logging.exception("Falha ao instanciar cliente Gemini")
            return None

    def parse_menu_with_gemini(self, meal_title: str, field_html: str) -> Optional[dict]:
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
            parsed: Optional[MenuResponse] = getattr(resp, "parsed", None)
            if not parsed:
                parsed = MenuResponse.model_validate_json(resp.text)
        except Exception:
            logging.exception("Erro no parsing estruturado do Gemini")
            return None

        sections = {}
        for attr, display in KEY_MAP.items():
            items = getattr(parsed.sections, attr)
            if items:
                sections[display] = items
        return {"meal": parsed.meal, "sections": sections}

    def get_menu_content(self) -> Optional[dict]:
        today = datetime.date.today()
        url = f"https://ru.ufes.br/cardapio/{today}"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            response = requests.get(url, headers=headers, timeout=20)
        except Exception:
            logging.exception("Erro ao obter cardápio")
            return None
        if response.status_code != 200:
            logging.warning("Site do RU respondeu %s", response.status_code)
            return None

        soup = BeautifulSoup(response.content, "html.parser")
        menu = {}
        titles = soup.find_all("div", class_="views-field-title")
        bodies = soup.find_all("div", class_="views-field-body")

        for title, body in zip(titles, bodies):
            title_span = title.find("span", class_="field-content")
            if not title_span:
                continue
            meal_title = title_span.get_text(strip=True)

            body_div = body.find("div", class_="field-content")
            field_html = str(body_div) if body_div else ""
            meal_text = body_div.get_text("\n", strip=True) if body_div else ""

            parsed = self.parse_menu_with_gemini(meal_title, field_html)
            key = "Almoço" if "Almoço" in meal_title else "Jantar" if "Jantar" in meal_title else None
            if not key:
                continue

            if parsed and parsed.get("sections"):
                menu[key] = parsed
            elif meal_text:
                menu[key] = {"meal": key, "sections": self._fallback_sections(meal_text)}
        return menu or None

    # --- Fallback parser when Gemini is unavailable ---

    def _fallback_sections(self, raw_text: str) -> dict:
        forbidden = ("sujeito", "informamos", "opção", "cardápio")
        sections: dict = {}
        current = None
        for raw in raw_text.split("\n"):
            line = raw.strip()
            if not line:
                continue
            if any(w in line.lower() for w in forbidden):
                continue
            base = line.split("(")[0].strip()
            if base in SECTION_EMOJIS:
                current = base
                sections.setdefault(current, [])
                continue
            if not current:
                continue
            for sub in (s.strip() for s in base.split(",")):
                if sub and len(sub) > 1 and sub not in sections[current]:
                    sections[current].append(sub)
        return sections

    # --- Formatting (channel-aware) ---

    def format_message(self, menu: dict, channel: str = "telegram") -> Optional[str]:
        if not menu:
            return None
        sections = (menu.get("sections") or {}).copy()
        if not sections.get("Acompanhamento"):
            sections["Acompanhamento"] = list(FIXED_ACCOMPANIMENTS)

        meal = menu.get("meal") or "Almoço"
        today = datetime.date.today().strftime("%d/%m/%Y")

        if channel == "whatsapp":
            return self._render_whatsapp(meal, today, sections)
        return self._render_telegram(meal, today, sections)

    @staticmethod
    def _normalize_items(items) -> list:
        if isinstance(items, str):
            items = [s.strip() for s in items.split("/") if s.strip()]
        else:
            items = [s.strip() for s in items if s and s.strip()]
        seen = set()
        out = []
        for item in items:
            key = item.lower()
            if key not in seen:
                seen.add(key)
                out.append(item)
        return out

    def _render_telegram(self, meal: str, today: str, sections: dict) -> str:
        lines = [f"<b>📅 {html.escape(meal)} do dia {today}</b>", ""]
        for key in SECTION_ORDER:
            items = self._normalize_items(sections.get(key) or [])
            if not items:
                continue
            emoji = SECTION_EMOJIS.get(key, "•")
            lines.append(f"{emoji} <b>{html.escape(key)}</b>:")
            for item in items:
                lines.append(f"    - {html.escape(item)}")
            lines.append("")
        return "\n".join(lines).rstrip()

    def _render_whatsapp(self, meal: str, today: str, sections: dict) -> str:
        lines = [f"*📅 {meal} do dia {today}*", ""]
        for key in SECTION_ORDER:
            items = self._normalize_items(sections.get(key) or [])
            if not items:
                continue
            emoji = SECTION_EMOJIS.get(key, "•")
            lines.append(f"{emoji} *{key}*:")
            for item in items:
                lines.append(f"  • {item}")
            lines.append("")
        return "\n".join(lines).rstrip()
