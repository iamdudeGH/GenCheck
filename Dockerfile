# GenCheck verification portal
# Build:  docker build -t gencheck-portal .
# Run:    docker run -p 8000:8000 -e GENCHECK_PRIVATE_KEY=0x... gencheck-portal
# (GENCHECK_PRIVATE_KEY is optional — without it only cached domains answer.)

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --pre -r requirements.txt fastapi "uvicorn[standard]"

COPY gencheck/ gencheck/
COPY contracts/ contracts/
COPY final_contract.json benchmark_fees.json ./
COPY portal/ portal/

EXPOSE 8000
CMD ["uvicorn", "portal.app:app", "--host", "0.0.0.0", "--port", "8000"]
