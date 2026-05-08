# Cardápio RU Bot

Coleta o cardápio do RU/UFES, formata e publica no **Telegram** e/ou **WhatsApp**.
Usa Google Gemini para extrair os itens do HTML, com fallback de parsing textual.

---

## Recursos

- Extração com IA (Gemini) + fallback.
- Envio formatado para canal do Telegram (HTML) e/ou grupo do WhatsApp (Markdown WA).
- Apaga **todas** as mensagens anteriores do mesmo tipo de refeição ao enviar uma nova.
- Limpeza diária à 23:59.
- HTML do Telegram com escape correto (sem mais quebra por `&`, `<`, `>`).
- Suporte a ambientes DEV/PROD e teste rápido de envio.

---

## Configuração

Variáveis de ambiente (`.env`):

### Comum
- `APP_ENV` (opcional): `dev` para usar tokens/canais de DEV.
- `GOOGLE_API_KEY`: chave da API Gemini (opcional; sem ela usa só fallback).

### Telegram (opcional — só envia se configurado)
- `TELEGRAM_TOKEN` / `TELEGRAM_DEV_TOKEN`
- `CHANNEL_ID` / `CHANNEL_DEV_ID` (prefira id numérico `-100...`)

### WhatsApp (opcional — só envia se configurado)
Compatível com **Evolution API** (open source, baseado em Baileys) ou qualquer gateway com endpoints
`POST /message/sendText/{instance}` e `DELETE /chat/deleteMessageForEveryone/{instance}`.

- `WHATSAPP_API_URL`: ex. `https://evo.meudominio.com`
- `WHATSAPP_API_KEY`: API key configurada na Evolution
- `WHATSAPP_INSTANCE`: nome da instância
- `WHATSAPP_GROUP_ID` / `WHATSAPP_DEV_GROUP_ID`: id do grupo no formato `123456789@g.us`

Pra descobrir o id do grupo, na Evolution: `GET /chat/findGroups/{instance}` e use o `id` retornado.

Pelo menos um canal (Telegram ou WhatsApp) precisa estar configurado.

### Exemplos

`.env.prod`
```env
TELEGRAM_TOKEN=xxxxx
CHANNEL_ID=-1001234567890
GOOGLE_API_KEY=xxxxx

WHATSAPP_API_URL=https://evo.meudominio.com
WHATSAPP_API_KEY=xxxxx
WHATSAPP_INSTANCE=cardapio-ru
WHATSAPP_GROUP_ID=120363000000000000@g.us
```

`.env.dev`
```env
APP_ENV=dev
TELEGRAM_DEV_TOKEN=xxxxx
CHANNEL_DEV_ID=-1009876543210
GOOGLE_API_KEY=xxxxx
WHATSAPP_API_URL=https://evo.meudominio.com
WHATSAPP_API_KEY=xxxxx
WHATSAPP_INSTANCE=cardapio-dev
WHATSAPP_DEV_GROUP_ID=120363111111111111@g.us
```

---

## Execução local

```bash
pip install -r requirements.txt
python main.py
```

Teste rápido (envia uma mensagem dummy nos canais configurados e sai):
```bash
TEST_DEV_SEND=1 python main.py
```

---

## Docker (manual)

```bash
docker build -t gabrielaltoe/cardapio_ru_ufes:latest .
docker run -d \
  --name cardapio_ru_bot \
  --restart unless-stopped \
  --env-file .env \
  -e DATA_DIR=/data \
  -v $(pwd)/data:/data \
  gabrielaltoe/cardapio_ru_ufes:latest
```

---

## Deploy automático (CI → VPS)

O `.github/workflows/deploy.yml` builda a imagem e dispara deploy na VPS a cada push em `main`:

1. Builda `gabrielaltoe/cardapio_ru_ufes:latest` e `:<sha-curto>`.
2. Pusha pro Docker Hub.
3. SSH na VPS, roda `docker compose pull && docker compose up -d` no diretório do deploy.

### Secrets do GitHub (repo → Settings → Secrets and variables → Actions)

| Secret | Descrição |
| --- | --- |
| `DOCKERHUB_USERNAME` | Usuário do Docker Hub |
| `DOCKERHUB_TOKEN` | Access token (Docker Hub → Account Settings → Security) |
| `SSH_HOST` | IP/hostname da VPS |
| `SSH_USER` | Usuário SSH (ex: `ubuntu`) |
| `SSH_KEY` | Conteúdo da chave **privada** SSH (ex: `~/.ssh/id_ed25519`) |
| `SSH_PORT` | Porta SSH (opcional, default 22) |
| `DEPLOY_PATH` | Caminho onde fica o `docker-compose.yml` na VPS, ex: `/srv/cardapio-ru` |

### Setup inicial na VPS

```bash
mkdir -p /srv/cardapio-ru/data
cd /srv/cardapio-ru
# coloca o .env com TELEGRAM_TOKEN, CHANNEL_ID, GOOGLE_API_KEY, WHATSAPP_*
# copia o docker-compose.yml deste repo pra cá
docker compose up -d
```

A partir daí, todo merge em `main` atualiza o container automaticamente.

### Disparo manual

Actions → "Build and deploy" → **Run workflow**.

---

## Como funciona

1. A cada 6 minutos verifica o cardápio do dia.
2. Tenta parsear com Gemini → estrutura JSON; senão, fallback textual.
3. Renderiza pra cada canal (Telegram em HTML escapado, WhatsApp em `*bold*`).
4. Envia, registra o id e apaga **todas** as mensagens anteriores do mesmo tipo (Almoço/Jantar) — não só uma.
5. Se um canal falhar, o outro ainda envia.
6. À 23:59 todas as mensagens registradas são apagadas.

Requisitos pra apagar:
- Telegram: bot precisa ser admin do canal, chat_id numérico.
- WhatsApp: gateway precisa suportar `deleteMessageForEveryone` e a mensagem precisa ter sido enviada pela própria instância.

---

## Troubleshooting

- **Telegram 400 / "can't parse entities"**: era causado por `&`, `<` ou `>` no cardápio — agora todos os campos dinâmicos são escapados.
- **Mensagem antiga não some**: confira que o bot é admin (Telegram) / que a instância tem permissão (WhatsApp). Telegram só permite deletar mensagens com até 48h.
- **WhatsApp 401/403**: verifique `WHATSAPP_API_KEY` e se a instância está conectada.
- **Gemini falha**: confirme `GOOGLE_API_KEY`; o fallback textual continua ativo.

---

## Licença

MIT.
