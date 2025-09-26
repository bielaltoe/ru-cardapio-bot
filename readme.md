# Cardápio RU Bot

Automatiza a coleta do cardápio do RU (site oficial), formata e publica no Telegram. Usa o Gemini para extrair dados estruturados do HTML e possui fallback para parsing tradicional.

---

## 🚀 Recursos

- 🤖 Extração com IA: parsing do HTML usando Google Gemini (google-genai), com fallback seguro.
- 💬 Integração Telegram: envio em HTML para canal.
- 🔄 Agendamento: verificação a cada 6 minutos.
- 🧹 Limpeza diária: exclusão automática das mensagens às 23:59.
- 🧪 Ambiente DEV/PROD: separação de tokens e canais por ambiente.
- ⚙️ Teste rápido: flag para disparar uma mensagem de teste e sair.

---

## 🛠️ Tecnologias

- Python 3.10+
- Bibliotecas:
  - requests, beautifulsoup4
  - schedule, logging
  - python-dotenv
  - google-genai (cliente oficial Gemini)
- Docker (opcional)

---

## ⚙️ Configuração

Crie um arquivo `.env` (ou `.env.dev` e `.env.prod`):

Obrigatórios:
- TELEGRAM_TOKEN: token do bot (PROD)
- CHANNEL_ID: id do canal principal (recomendado numérico, ex.: -100XXXXXXXXXX)

Opcionais/DEV:
- APP_ENV=dev
- TELEGRAM_DEV_TOKEN: token do bot de DEV
- CHANNEL_DEV_ID: id do canal de DEV (numérico)

Gemini:
- GEMINI_API_KEY: chave da API Gemini

Exemplos:

.env.dev
- APP_ENV=dev
- TELEGRAM_DEV_TOKEN=seu_token_dev
- CHANNEL_DEV_ID=-100XXXXXXXXXX
- GEMINI_API_KEY=sua_chave

.env.prod
- TELEGRAM_TOKEN=seu_token_prod
- CHANNEL_ID=-100YYYYYYYYYY
- GEMINI_API_KEY=sua_chave

Como obter o id do canal (chat_id):
- Adicione o bot como Administrador do canal.
- Envie uma mensagem no canal.
- Se o canal tiver @username: GET https://api.telegram.org/bot<TOKEN>/getChat?chat_id=@seu_username
- Se for privado: GET https://api.telegram.org/bot<TOKEN>/getUpdates e procure `.channel_post.chat.id` (ex.: -100XXXXXXXXXX)

---

## 🖥️ Instalação e Execução Local

1) Instale dependências
- pip install -r requirements.txt

2) Configure `.env` (ou `.env.dev`/`.env.prod`)

3) Teste rápido no canal atual
- TEST_DEV_SEND=1 python api.py

4) Execução normal (agendador + limpeza diária)
- python api.py

Observações
- Com APP_ENV=dev, o código usa TELEGRAM_DEV_TOKEN e CHANNEL_DEV_ID.
- Prefira IDs numéricos para garantir compatibilidade com deleteMessage.

---

## 🐳 Executar com Docker

Certifique-se de ter o arquivo `.env` na pasta do container.

- docker run -d \
  --name cardapio_ru_bot \
  --restart unless-stopped \
  --env-file .env \
  gabrielaltoe/cardapio_ru_ufes:latest

Para DEV, coloque APP_ENV=dev e variáveis de DEV no `.env` consumido pelo container.

---

## 🔍 Como funciona

1) Coleta do site do RU no dia atual.
2) Tenta parse com Gemini para gerar um dicionário de seções (Salada, Prato Principal, etc.).
3) Se Gemini indisponível ou falhar, usa parsing textual como fallback.
4) Formata a mensagem (incluindo data) e envia ao Telegram.
5) Deduplica por refeição utilizando hash por Almoço/Jantar e só envia se houver alteração.
6) Exclui mensagens diariamente às 23:59.

Requisitos para exclusão funcionar
- Bot deve ser Admin do canal.
- Use chat_id numérico.

---

## ❗ Boas práticas de segurança

- Nunca versione `.env` ou segredos. Rotacione tokens se tiver exposto.
- Adicione ao .gitignore: `.env`, `.env.*`, `app.log`, `message_ids.txt`.

---

## 🧰 Troubleshooting

- 403/400 ao enviar: verifique se o bot é Admin e se o chat_id está correto.
- deleteMessage falha: use id numérico e confirme permissão de excluir mensagens.
- Gemini não responde: confirme GEMINI_API_KEY e conectividade. O fallback seguirá ativo.

---

## 🤝 Contribuições

- Fork, branch, PR. Descrições claras são bem-vindas.

---

## 📜 Licença

MIT.

---

## 📧 Contato

Canal: @cardapio_ufes
```

