FROM python:3.12.1

# Set the working directory inside the container
WORKDIR /backend/TataPowerBackend

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

# Add this environment variable to see Python print statements immediately
ENV PYTHONUNBUFFERED=1

COPY . .

EXPOSE 7001

# Modified command to print environment variables before starting
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7001"]
