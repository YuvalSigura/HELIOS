FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --system --uid 10001 helios
COPY --chown=helios:helios helios ./helios
USER helios
CMD ["uvicorn", "helios.web:app", "--host", "0.0.0.0", "--port", "8000"]
