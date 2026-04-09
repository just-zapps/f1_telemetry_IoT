FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY producer.py openf1_client.py ./
RUN mkdir -p /app/cache

CMD ["python", "-u", "producer.py"]