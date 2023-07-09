FROM docker.io/library/python:3

EXPOSE 8025

WORKDIR /smtp-to-line

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN mkdir data

COPY server.py ./
CMD [ "python", "./server.py"]