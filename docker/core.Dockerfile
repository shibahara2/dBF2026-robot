FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-core.txt ./
RUN pip install --no-cache-dir -r requirements-core.txt

COPY app ./app
COPY mocks ./mocks
COPY run.py run_mocks.py ./

CMD ["python", "run.py"]
