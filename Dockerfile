FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Define o diretório de trabalho dentro do container
WORKDIR /usr/src/app

# Copia os arquivos do projeto para o container
COPY main.py ./
COPY tools.py ./
COPY config.py ./
COPY requirements.txt ./

# Configuração do fuso horário
ENV TZ=America/Sao_Paulo
RUN apt-get update && apt-get install -y tzdata && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    apt-get clean

# Instala as dependências do Python
RUN pip install --no-cache-dir -r requirements.txt

# Comando para iniciar o script
CMD ["python", "./main.py"]
