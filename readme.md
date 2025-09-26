# Cardápio RU Bot

Automatiza a coleta do cardápio do RU (site oficial), formata e publica no Telegram.
Utiliza Google Gemini para extrair dados estruturados do HTML, com fallback para parsing tradicional.

---

## Recursos

- Extração com IA (Gemini) + fallback seguro.
- Envio formatado (HTML) para canal do Telegram.
- Agendamento periódico (a cada 6 minutos).
- Limpeza diária de mensagens (23:59).
- Suporte a ambientes DEV/PROD e teste rápido de envio.

---

## Tecnologias

- Python 3.10+
- requests, beautifulsoup4, schedule, logging, python-dotenv
- google-genai (cliente oficial Gemini)
- Docker (opcional)

---

## Configuração

Crie um arquivo `.env` (ou use `.env.dev` e `.env.prod`):

Obrigatórios (PROD):
- TELEGRAM_TOKEN: token do bot de produção
- CHANNEL_ID: id do canal principal (prefira numérico, ex.: -100XXXXXXXXXX)

Opcionais (DEV):
- APP_ENV=dev
- TELEGRAM_DEV_TOKEN: token do bot de DEV
- CHANNEL_DEV_ID: id do canal de DEV (numérico)

Gemini:
- GEMINI_API_KEY: chave da API Gemini

Exemplos:

.env.dev
```env
APP_ENV=dev
TELEGRAM_DEV_TOKEN=SEU_TOKEN_DEV
CHANNEL_DEV_ID=-100XXXXXXXXXX
GEMINI_API_KEY=SUA_CHAVE_GEMINI
```

.env.prod
```env
TELEGRAM_TOKEN=SEU_TOKEN_PROD
CHANNEL_ID=-100YYYYYYYYYY
GEMINI_API_KEY=SUA_CHAVE_GEMINI
```

Como obter o chat_id do canal:
- Adicione o bot como Administrador do canal.
- Envie uma mensagem no canal.
- Se tiver @username: GET https://api.telegram.org/bot<TOKEN>/getChat?chat_id=@seu_username
- Se for privado: GET https://api.telegram.org/bot<TOKEN>/getUpdates e procure `.channel_post.chat.id` (formato -100XXXXXXXXXX)

---

## Instalação e execução local

1) Instale dependências
```bash
pip install -r requirements.txt
```

2) Configure `.env` (ou `.env.dev` / `.env.prod`)

3) Teste rápido no canal atual
```bash
TEST_DEV_SEND=1 python api.py
```

4) Execução normal (agendador + limpeza diária)
```bash
python api.py
```

Observações:
- Com APP_ENV=dev, o código usa TELEGRAM_DEV_TOKEN e CHANNEL_DEV_ID.
- Prefira IDs numéricos para compatibilidade com deleteMessage.

---

## Docker

Build da imagem:
```bash
docker build -t gabrielaltoe/cardapio_ru_ufes:latest .
```

Rodar com .env local:
```bash
docker run -d \
  --name cardapio_ru_bot \
  --restart unless-stopped \
  --env-file .env \
  gabrielaltoe/cardapio_ru_ufes:latest
```

Teste rápido (DEV):
```bash
docker run --rm --env-file .env -e TEST_DEV_SEND=1 gabrielaltoe/cardapio_ru_ufes:latest
```

Dica: mantenha `.env` fora da imagem (adicione `.env` e `.env.*` no `.dockerignore`/`.gitignore`).

---

## Como funciona

1) Coleta o HTML do dia no site do RU.
2) Tenta extrair seções com Gemini (Salada, Prato Principal, etc.).
3) Se falhar, aplica parsing textual como fallback.
4) Formata a mensagem (com data) e envia ao Telegram.
5) Deduplica por refeição via hash (Almoço/Jantar) e só envia se houver alteração.
6) Exclui mensagens diariamente às 23:59.

Requisitos para excluir:
- Bot deve ser Admin do canal.
- Use chat_id numérico.

---

## Segurança

- Não versione `.env` ou segredos; rotacione tokens/chaves se expuser.
- Adicione ao .gitignore: `.env`, `.env.*`, `app.log`, `message_ids.txt`.

---

## Troubleshooting

- 400/403 ao enviar: verifique se o bot é Admin e o chat_id está correto.
- deleteMessage falha: use id numérico e confirme permissão de exclusão.
- Gemini indisponível: confirme GEMINI_API_KEY e rede; o fallback segue ativo.

---

## Licença

MIT.

---

## Contato

Canal: @cardapio_ufes