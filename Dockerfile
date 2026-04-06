FROM python:3.12-slim

# build-essential needed for zeroc-ice native extension
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (includes slice2py)
COPY livekit-auth/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Compile Murmur.ice → message_history/generated/Murmur_ice.py
COPY message-history/proto/Murmur.ice ./proto/Murmur.ice
RUN mkdir -p message_history/generated && \
    python3 -c "\
import Ice, os, subprocess, sys; \
slice_dir = os.path.join(os.path.dirname(Ice.__file__), 'slice'); \
subprocess.run( \
  ['slice2py', '-I', slice_dir, '--output-dir', 'message_history/generated', 'proto/Murmur.ice'], \
  check=True \
)"

# Copy app source
COPY livekit-auth/main.py .
COPY message-history/__init__.py       message_history/__init__.py
COPY message-history/db.py             message_history/db.py
COPY message-history/ice_listener.py   message_history/ice_listener.py
COPY message-history/api.py            message_history/api.py
# generated/__init__.py is already present from the slice2py step,
# but copy ours to ensure the package is importable even if slice fails
COPY message-history/generated/__init__.py message_history/generated/__init__.py

EXPOSE 3000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3000"]
