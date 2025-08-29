# Use Python slim image
FROM python:3.11-slim

# Install dependencies
RUN pip install --no-cache-dir PyYAML reportlab

# Copy application
COPY yaml-to-pdf.py /app/yaml-to-pdf.py

# Set working directory for user data
WORKDIR /data

# Run the script by default
ENTRYPOINT ["python", "/app/yaml-to-pdf.py"]
CMD ["--help"]
