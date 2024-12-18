FROM python:3.10.0


COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV HOST_NAME="postgres"

ENV USER="postgres"

ENV PASSWORD="siri2251105"

ENV HOST="172.18.100.54"

ENV DATABASE="Tata_Power"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "6969"]