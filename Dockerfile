FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg curl git && \
    pip install --upgrade pip

WORKDIR /app
COPY . /app

RUN pip install -r requirements.txt

CMD ["python", "bot.py"]
