# Use the official Python 3.9 slim image
FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    sshpass \
    gcc \
    libssl-dev \
    openssh-client \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir ansible

# Create .ssh directory and set permissions
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh

# Copy the private key from the 'keys' folder to the .ssh directory
COPY keys/id_rsa /root/.ssh/id_rsa

# Set correct permissions for the SSH private key
RUN chmod 600 /root/.ssh/id_rsa

# Copy the requirements.txt and install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy environment example
COPY env.example /app/.env.example

COPY . /app
COPY ./ansible_playbooks /app/ansible_playbooks/

# Create an entrypoint script to start both the FastAPI server and Celery worker
RUN echo '#!/bin/sh' > /entrypoint.sh && \
    echo 'uvicorn crud.api:app --host 0.0.0.0 --port 80 &' >> /entrypoint.sh && \
    echo 'celery -A db.celery_app worker --loglevel=info' >> /entrypoint.sh && \
    chmod +x /entrypoint.sh

# Use the entrypoint script as the default command
CMD ["/bin/sh", "/entrypoint.sh"]