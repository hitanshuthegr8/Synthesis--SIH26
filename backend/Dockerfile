FROM python:3.12-slim

WORKDIR /app

# Ensure requirements.txt exists in backend folder before building
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
