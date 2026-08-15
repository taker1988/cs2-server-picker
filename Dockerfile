FROM python:3.11-alpine

WORKDIR /app

COPY generate.py /app/generate.py

EXPOSE 8000

CMD sh -c "python /app/generate.py & sleep 5 && python -m http.server 8000 --directory /app/html"
