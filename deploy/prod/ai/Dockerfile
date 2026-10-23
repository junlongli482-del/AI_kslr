FROM python:3.12-slim
WORKDIR /app/apps/ai
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple fastapi "uvicorn[standard]" httpx pypdfium2 pillow python-dotenv pydantic \
    || pip install --no-cache-dir fastapi "uvicorn[standard]" httpx pypdfium2 pillow python-dotenv pydantic
COPY apps/ai /app/apps/ai
RUN mkdir -p /data
EXPOSE 2003
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "2003"]
