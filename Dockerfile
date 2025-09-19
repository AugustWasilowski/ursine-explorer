# Ursine Explorer Docker Container
FROM ubuntu:22.04

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-requests \
    python3-serial \
    python3-numpy \
    hackrf \
    libhackrf-dev \
    git \
    build-essential \
    pkg-config \
    libusb-1.0-0-dev \
    libncurses-dev \
    libncurses5-dev \
    net-tools \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Build dump1090 from source
WORKDIR /tmp
RUN git clone https://github.com/flightaware/dump1090.git && \
    cd dump1090 && \
    make && \
    cp dump1090 /usr/local/bin/ && \
    chmod +x /usr/local/bin/dump1090 && \
    cd / && \
    rm -rf /tmp/dump1090

# Create application directory
WORKDIR /app

# Copy application files
COPY *.py ./
COPY *.json ./
COPY *.sh ./

# Make scripts executable
RUN chmod +x *.sh

# Create non-root user
RUN useradd -r -s /bin/false ursine && \
    usermod -a -G plugdev ursine

# Set up udev rules for HackRF
RUN echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="6089", GROUP="plugdev", MODE="0664"' > /etc/udev/rules.d/53-hackrf.rules

# Create directories for data
RUN mkdir -p /tmp/adsb_json && \
    chown -R ursine:ursine /app /tmp/adsb_json

# Expose ports
EXPOSE 8080 8081

# Switch to non-root user
USER ursine

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/data/aircraft.json || exit 1

# Default command
CMD ["python3", "adsb_receiver.py"]
